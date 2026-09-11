"""Run trusted local SQLHarness controls against gate spies without importing live bridge.

Uses the actual harness base and extract_sql function; solver/database/config are
synthetic. This tests the interface adapter, not full provider runtime restoration.
The yielded callable is serial-only. This is not an isolation sandbox for untrusted code.
"""
import ast
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import re
import sys
import types
import uuid

from experiment.revision.gate_v2 import SCHEMA
from experiment.revision.replay import ROOT


@contextmanager
def candidate(path):
    path=Path(path).resolve()
    runtime=ROOT/'external/TTHE/text_to_sql'
    if not path.is_relative_to(runtime/'agents') or not path.is_file():
        raise ValueError('expected a local TTHE agents file')
    prefix='_gate_probe_'+uuid.uuid4().hex
    package=types.ModuleType(prefix)
    package.__path__=[str(runtime)]
    agents=types.ModuleType(prefix+'.agents')
    agents.__path__=[str(runtime/'agents')]
    bridge=types.ModuleType(prefix+'.bridge')
    active=[]
    def solver(prompt,system='',temperature=0.,n=1,seq=0):
        result=active[-1].llm(prompt,system=system,temperature=temperature,n=n)
        active[-1].trace[-1]['seq']=seq
        return result
    bridge.solver_llm=solver
    bridge.execute=lambda db,sql: db.execute(sql)
    # Compile only the original pure extraction function, avoiding LLM clients,
    # dataset initialization and provider configuration imports.
    source=ROOT/'external/TTHE/ase/llm.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='extract_sql')
    namespace={'re':re}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
    bridge.extract_sql=namespace['extract_sql']
    sys.modules.update({prefix:package,prefix+'.agents':agents,prefix+'.bridge':bridge})
    try:
        spec=importlib.util.spec_from_file_location(prefix+'.agents.'+path.stem,path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        base=sys.modules[prefix+'.harness_base'].SQLHarness
        classes=[v for v in vars(module).values() if isinstance(v,type) and v is not base
                 and issubclass(v,base) and v.__module__==module.__name__]
        if len(classes)!=1:
            raise ValueError('expected exactly one locally defined SQLHarness class')
        class Database:
            db_id='gate_v2_synthetic'
            schema={'tables':[{'name':'ledger','columns':[{'name':'id','type':'INTEGER','pk':True},
                        {'name':'amount','type':'REAL','pk':False}]},
                       {'name':'unused','columns':[{'name':'label','type':'TEXT','pk':False}]}],
                    'foreign_keys':[]}
            def schema_text(self):
                return SCHEMA
            def execute(self,sql,timeout=30.,limit=20000):
                return active[-1].execute(sql)
        def solve(io,question):
            active.append(io)
            try:
                return classes[0](Database()).solve(question)
            finally:
                active.pop()
        yield solve
    finally:
        for name in list(sys.modules):
            if name==prefix or name.startswith(prefix+'.'):
                del sys.modules[name]

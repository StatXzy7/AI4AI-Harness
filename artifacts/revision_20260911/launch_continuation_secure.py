import sqlite3,json,os,runpy,sys
os.chdir(r'E:\projects\AI4AI-Harness'); sys.path.insert(0,os.getcwd())
c=sqlite3.connect('file:C:/Users/Administrator/.cc-switch/cc-switch.db?mode=ro',uri=True); d=json.loads(c.execute("select settings_config from providers where name='paratera-glm-ziqian'").fetchone()[0]); c.close(); os.environ.update(d['env']); os.environ['PARATERA_API_KEY']=d['env']['ANTHROPIC_AUTH_TOKEN']
sys.argv=['common_pool_continuation','--config','artifacts/revision_20260911/common_pool_qwen_continuation_73/config.json']; runpy.run_module('experiment.revision.common_pool_continuation',run_name='__main__')

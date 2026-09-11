"""Windows process-tree lifetime for a gated trusted worker, not a security sandbox.

See Microsoft Learn /windows/win32/procthread/job-objects. No breakaway flags.
The caller opens the worker's start gate only after assigning it to this job.
"""
import ctypes as c
from ctypes import wintypes as w
import _winapi
import msvcrt
import os
import subprocess
import time


class BasicLimits(c.Structure):
    _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong),
                ('flags', w.DWORD), ('min_working_set', c.c_size_t), ('max_working_set', c.c_size_t),
                ('active_limit', w.DWORD), ('affinity', c.c_size_t),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class IoCounters(c.Structure):
    _fields_ = [(name, c.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops',
                                                  'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(c.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', c.c_size_t),
                ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]


class Accounting(c.Structure):
    _fields_ = [(name, c.c_longlong) for name in ('user_time', 'kernel_time', 'period_user', 'period_kernel')]
    _fields_ += [(name, w.DWORD) for name in ('page_faults', 'total', 'active', 'terminated')]


KERNEL = c.WinDLL('kernel32', use_last_error=True)
KERNEL.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
KERNEL.CreateJobObjectW.restype = w.HANDLE
KERNEL.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
KERNEL.SetInformationJobObject.restype = w.BOOL
KERNEL.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
KERNEL.AssignProcessToJobObject.restype = w.BOOL
KERNEL.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
KERNEL.QueryInformationJobObject.restype = w.BOOL
KERNEL.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
KERNEL.TerminateJobObject.restype = w.BOOL
KERNEL.CloseHandle.argtypes = [w.HANDLE]
KERNEL.CloseHandle.restype = w.BOOL
KERNEL.ResumeThread.argtypes = [w.HANDLE]
KERNEL.ResumeThread.restype = w.DWORD


def checked(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


class WindowsJob:
    def __enter__(self):
        self.handle = KERNEL.CreateJobObjectW(None, None)
        checked(self.handle)
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            checked(KERNEL.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)))
        except BaseException:
            KERNEL.CloseHandle(self.handle)
            raise
        return self

    def assign(self, process):
        checked(KERNEL.AssignProcessToJobObject(self.handle, int(process._handle)))

    def accounting(self):
        info = Accounting()
        checked(KERNEL.QueryInformationJobObject(self.handle, 1, c.byref(info), c.sizeof(info), None))
        return {'total_processes': info.total, 'active_processes': info.active,
                'limit_terminated_processes': info.terminated}

    def terminate(self):
        checked(KERNEL.TerminateJobObject(self.handle, 3))

    def wait_empty(self, seconds=5):
        deadline = time.monotonic() + seconds
        while True:
            info = self.accounting()
            if info['active_processes'] == 0:
                return info
            if time.monotonic() >= deadline:
                raise RuntimeError('Job still contains live processes; cannot advance acquisition')
            time.sleep(0.02)

    def __exit__(self, *_args):
        checked(KERNEL.CloseHandle(self.handle))


class SuspendedWorker:
    """Keep the primary thread suspended until Job assignment, including venv launchers."""
    def __init__(self, command, cwd, stdout, stderr):
        self.command = command
        self.returncode = None
        with open(os.devnull, 'rb') as stdin:
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, stdout, stderr)]
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            startup.lpAttributeList = {'handle_list': list(dict.fromkeys(handles))}
            previous = [os.get_handle_inheritable(h) for h in handles]
            try:
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                self._handle, self._thread, self.pid, _tid = _winapi.CreateProcess(
                    None, subprocess.list2cmdline(command), None, None, True,
                    subprocess.CREATE_NO_WINDOW | 0x4, None, str(cwd), startup)  # CREATE_SUSPENDED
            finally:
                for handle, inherited in zip(handles, previous):
                    os.set_handle_inheritable(handle, inherited)

    def resume(self):
        if KERNEL.ResumeThread(self._thread) == 0xFFFFFFFF:
            raise c.WinError(c.get_last_error())
        _winapi.CloseHandle(self._thread)
        self._thread = None

    def poll(self):
        if _winapi.WaitForSingleObject(self._handle, 0) == _winapi.WAIT_OBJECT_0:
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def wait(self, timeout):
        if _winapi.WaitForSingleObject(self._handle, max(1, int(timeout * 1000))) == _winapi.WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(self.command, timeout)
        self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def kill(self):
        _winapi.TerminateProcess(self._handle, 3)

    def close(self):
        if self._thread is not None:
            _winapi.CloseHandle(self._thread)
        _winapi.CloseHandle(self._handle)

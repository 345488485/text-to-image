"""Watch only a snapshot of an owned Windows process tree using non-reusable handles."""
from contextlib import contextmanager


@contextmanager
def watch_windows_tree(pid):
    import ctypes
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    class Entry(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                    ('exe', w.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        fn = getattr(kernel, name); fn.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]; fn.restype = w.BOOL
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]; kernel.CloseHandle.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; kernel.WaitForSingleObject.restype = w.DWORD
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}; entry = Entry(); entry.size = ctypes.sizeof(entry)
    try:
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        if not found:
            raise ctypes.WinError(ctypes.get_last_error())
        while found:
            parents[entry.pid] = entry.parent
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(snapshot)
    owned = {pid}
    while True:
        expanded = owned | {child for child, parent in parents.items() if parent in owned}
        if expanded == owned: break
        owned = expanded
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]; kernel.TerminateProcess.restype = w.BOOL
    handles = []
    try:
        for child in owned:
            handle = kernel.OpenProcess(0x100001, False, child)  # SYNCHRONIZE | PROCESS_TERMINATE, owned snapshot only
            if not handle:
                error = ctypes.get_last_error()
                if error == 87: continue  # Already exited before OpenProcess.
                raise ctypes.WinError(error)
            handles.append(handle)
        def stopped():
            return all(kernel.WaitForSingleObject(handle, 0) == 0 for handle in handles)
        def terminate():
            for handle in handles:
                if kernel.WaitForSingleObject(handle, 0) != 0:
                    if not kernel.TerminateProcess(handle, 1) and kernel.WaitForSingleObject(handle, 0) != 0:
                        raise ctypes.WinError(ctypes.get_last_error())
            for handle in handles:
                kernel.WaitForSingleObject(handle, 15000)
        stopped.terminate = terminate
        yield stopped
    finally:
        for handle in handles: kernel.CloseHandle(handle)


def windows_command_line(pid):
    import ctypes
    from ctypes import wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    n = ctypes.WinDLL('ntdll')
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; k.OpenProcess.restype=w.HANDLE
    k.CloseHandle.argtypes=[w.HANDLE]
    n.NtQueryInformationProcess.argtypes=[w.HANDLE,w.ULONG,w.LPVOID,w.ULONG,ctypes.POINTER(w.ULONG)]
    n.NtQueryInformationProcess.restype=w.LONG
    class Text(ctypes.Structure):
        _fields_=[('length',w.USHORT),('maximum',w.USHORT),('buffer',ctypes.c_void_p)]
    h=k.OpenProcess(0x1000,False,pid)
    if not h:
        if ctypes.get_last_error()==87: return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size=w.ULONG(); n.NtQueryInformationProcess(h,60,None,0,ctypes.byref(size))
        if not size.value: return None
        buffer=ctypes.create_string_buffer(size.value)
        status=n.NtQueryInformationProcess(h,60,buffer,len(buffer),ctypes.byref(size))
        if status: raise OSError('Cannot verify process command line: '+str(status))
        text=Text.from_buffer(buffer)
        return ctypes.wstring_at(text.buffer,text.length//2)
    finally: k.CloseHandle(h)

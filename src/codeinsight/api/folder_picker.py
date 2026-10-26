"""Windows 现代文件夹选择框；仅在独立的桌面子进程中运行 COM。"""

from __future__ import annotations

import ctypes
import json
import sys
import uuid


def choose_windows_folder() -> str | None:
    """返回真实文件系统路径；取消返回 None，所有 COM 接口与内存成对释放。"""
    if sys.platform != "win32":
        raise OSError("现代系统选择框仅适用于 Windows")

    from ctypes import wintypes

    ole32 = ctypes.OleDLL("ole32")
    hresult = ctypes.c_int32
    pointer = ctypes.c_void_p
    guid_type = ctypes.c_ubyte * 16
    ole32.CoInitializeEx.argtypes = [pointer, wintypes.DWORD]
    ole32.CoInitializeEx.restype = hresult
    ole32.CoCreateInstance.argtypes = [
        pointer,
        pointer,
        wintypes.DWORD,
        pointer,
        ctypes.POINTER(pointer),
    ]
    ole32.CoCreateInstance.restype = hresult
    ole32.CoTaskMemFree.argtypes = [pointer]
    ole32.CoTaskMemFree.restype = None

    def checked(result: int) -> None:
        if result < 0:
            raise OSError(f"系统文件夹窗口失败（HRESULT 0x{result & 0xFFFFFFFF:08X}）")

    def invoke(instance: pointer, slot: int, result_type, arg_types: tuple, *arguments):
        # 槽位来自 Windows SDK 的 IFileDialog / IShellItem，避免引入 COM 包。
        table = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(pointer))).contents
        method = ctypes.WINFUNCTYPE(result_type, pointer, *arg_types)(table[slot])
        return method(instance, *arguments)

    initialized = ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    checked(initialized)
    dialog, item, path = pointer(), pointer(), pointer()
    try:
        clsid = guid_type.from_buffer_copy(
            uuid.UUID("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7").bytes_le
        )
        iid = guid_type.from_buffer_copy(uuid.UUID("D57C7288-D4AD-4768-BE02-9D969532D960").bytes_le)
        checked(
            ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(dialog)
            )
        )
        options = wintypes.DWORD()
        checked(
            invoke(dialog, 10, hresult, (ctypes.POINTER(wintypes.DWORD),), ctypes.byref(options))
        )
        # PICKFOLDERS / FORCEFILESYSTEM / PATHMUSTEXIST / NOCHANGEDIR / DONTADDTORECENT。
        checked(
            invoke(
                dialog,
                9,
                hresult,
                (wintypes.DWORD,),
                options.value | 0x20 | 0x40 | 0x800 | 0x8 | 0x02000000,
            )
        )
        checked(invoke(dialog, 17, hresult, (wintypes.LPCWSTR,), "选择 Git 项目文件夹"))
        checked(invoke(dialog, 18, hresult, (wintypes.LPCWSTR,), "选择此文件夹"))
        # 后端没有桌面主窗口，使用自己的不可见置顶 owner，避免选择框被浏览器挡住。
        # 不能借用前台终端：终端销毁会连带取消选择框。
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            pointer,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        owner = user32.CreateWindowExW(
            0x88,
            "STATIC",
            "CodeInsight",
            0x80000000,
            user32.GetSystemMetrics(0) // 2,
            user32.GetSystemMetrics(1) // 2,
            0,
            0,
            None,
            None,
            None,
            None,
        )
        if not owner:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            result = invoke(dialog, 3, hresult, (wintypes.HWND,), owner)
        finally:
            user32.DestroyWindow(owner)
        if result & 0xFFFFFFFF == 0x800704C7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            return None
        checked(result)
        checked(invoke(dialog, 20, hresult, (ctypes.POINTER(pointer),), ctypes.byref(item)))
        checked(
            invoke(
                item,
                5,
                hresult,
                (wintypes.DWORD, ctypes.POINTER(pointer)),
                0x80058000,
                ctypes.byref(path),
            )
        )
        return ctypes.wstring_at(path)
    finally:
        if path:
            ole32.CoTaskMemFree(path)
        if item:
            invoke(item, 2, wintypes.ULONG, ())
        if dialog:
            invoke(dialog, 2, wintypes.ULONG, ())
        ole32.CoUninitialize()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"root_path": choose_windows_folder()}, ensure_ascii=False))

"""HWP/HWPX text extraction helpers."""

import os
import re
import subprocess
import logging


def _hwpx_zipxml(path: str) -> str:
    """HWPX(ZIP+XML) 파일에서 텍스트 추출"""
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(path, 'r') as z:
            texts = []
            for name in sorted(z.namelist()):
                if re.search(r'[Ss]ection\d+\.xml', name):
                    root = ET.fromstring(z.read(name).decode('utf-8', 'ignore'))
                    for el in root.iter():
                        if el.text and el.text.strip():
                            texts.append(el.text.strip())
            return '\n'.join(texts)
    except Exception as exc:
        logging.debug("HWPX 텍스트 추출 실패: %s", exc)
        return ''


def _hwp_win32com(path: str) -> str:
    hwp = None
    try:
        import win32com.client as client
        hwp = client.gencache.EnsureDispatch('HWPFrame.HwpObject')
        hwp.RegisterModule('FilePathCheckDLL', 'FilePathCheckerModule')
        hwp.Open(path, 'HWP', 'forceopen:true')
        return hwp.GetTextFile('TEXT', '').strip()
    except Exception as exc:
        logging.debug("HWP COM 텍스트 추출 실패: %s", exc)
        return ''
    finally:
        if hwp is not None:
            try:
                hwp.Quit()
            except Exception as exc:
                logging.debug("HWP COM 종료 실패: %s", exc)


def _hwp_olefile(path: str) -> str:
    """
    olefile로 HWP 5.x 바이너리 직접 명단 추출.
    BodyText/Section* 스트림에서 HWPTAG_PARA_TEXT(tag=67) 레코드 추출.
    """
    try:
        import olefile
        import zlib
        import struct
    except ImportError:
        return ''
    ole = None
    try:
        ole = olefile.OleFileIO(path)
        header = ole.openstream('FileHeader').read()
        compressed = bool(struct.unpack_from('<I', header, 36)[0] & 1)
        texts = []
        for i in range(100):
            sname = f'BodyText/Section{i}'
            if not ole.exists(sname):
                break
            data = ole.openstream(sname).read()
            if compressed:
                try:
                    data = zlib.decompress(data, -15)
                except Exception as exc:
                    logging.debug("HWP 압축 해제 실패: %s", exc)
            offset = 0
            while offset + 4 <= len(data):
                hw = struct.unpack_from('<I', data, offset)[0]
                tag = hw & 0x3FF
                size = (hw >> 20) & 0xFFF
                if size == 0xFFF:
                    size = struct.unpack_from('<I', data, offset + 4)[0]
                    offset += 4
                offset += 4
                if tag == 67 and offset + size <= len(data):
                    chunk = data[offset:offset + size]
                    txt = ''.join(
                        chr(struct.unpack_from('<H', chunk, j)[0])
                        for j in range(0, len(chunk) - 1, 2)
                        if struct.unpack_from('<H', chunk, j)[0] >= 0x20
                    ).strip()
                    if txt:
                        texts.append(txt)
                offset += size
        return '\n'.join(texts)
    except Exception as exc:
        logging.debug("HWP OLE 텍스트 추출 실패: %s", exc)
        return ''
    finally:
        if ole is not None:
            try:
                ole.close()
            except Exception as exc:
                logging.debug("HWP OLE 종료 실패: %s", exc)


def extract_hwp_text(filepath: str) -> str:
    """HWP / HWPX 파일에서 텍스트 추출 (3가지 방법 순차 시도)"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.hwpx':
        return _hwpx_zipxml(filepath)
    text = _hwp_win32com(filepath)
    if text:
        return text
    text = _hwp_olefile(filepath)
    if text:
        return text
    try:
        result = subprocess.run(
            ['hwp5txt', filepath], capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:
        logging.debug("hwp5txt 텍스트 추출 실패: %s", exc)
    return ''

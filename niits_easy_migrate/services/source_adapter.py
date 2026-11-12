# -*- coding: utf-8 -*-
import csv
import io
import os
import datetime
from odoo.exceptions import UserError
from odoo import _

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None


class BaseSourceAdapter:
    """Base interface for all data source adapters."""
    def read_headers(self, raw_data, filename=""):
        raise NotImplementedError

    def read_rows(self, raw_data, filename="", limit=None, offset=0):
        raise NotImplementedError

    def get_total_rows(self, raw_data, filename=""):
        raise NotImplementedError


class FileAdapter(BaseSourceAdapter):
    """Adapter for CSV, XLSX, and XLS file sources."""

    @staticmethod
    def _is_excel(raw_data, filename=""):
        if filename and filename.lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xls')):
            return True
        # Check ZIP / XLSX magic number PK\x03\x04
        if raw_data and len(raw_data) >= 4 and raw_data[:4] == b'PK\x03\x04':
            return True
        # Check OLE2 compound document magic for .xls
        if raw_data and len(raw_data) >= 8 and raw_data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            return True
        return False

    def read_headers(self, raw_data, filename=""):
        if not raw_data:
            return []
        if self._is_excel(raw_data, filename):
            return self._read_headers_excel(raw_data, filename)
        return self._read_headers_csv(raw_data)

    def _read_headers_excel(self, raw_data, filename=""):
        if openpyxl:
            try:
                wb = openpyxl.load_workbook(filename=io.BytesIO(raw_data), read_only=True, data_only=True)
                sheet = wb.active
                for row in sheet.iter_rows(max_row=1, values_only=True):
                    headers = [str(cell).strip() if cell is not None else f"Column_{idx+1}" for idx, cell in enumerate(row)]
                    wb.close()
                    return headers
                wb.close()
                return []
            except Exception:
                pass

        if xlrd:
            book = xlrd.open_workbook(file_contents=raw_data)
            sheet = book.sheet_by_index(0)
            if sheet.nrows > 0:
                row = sheet.row_values(0)
                return [str(cell).strip() if cell is not None and str(cell).strip() else f"Column_{idx+1}" for idx, cell in enumerate(row)]
            return []

        raise UserError(_("Neither openpyxl nor xlrd library is installed for Excel reading."))

    def _read_headers_csv(self, raw_data):
        # Support utf-8, utf-8-sig (BOM), windows-1252, latin-1
        text = self._decode_csv(raw_data)
        sample = text[:4096]
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ',' if ',' in sample else ';'
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for row in reader:
            return [col.strip() for col in row]
        return []

    def read_rows(self, raw_data, filename="", limit=None, offset=0):
        if not raw_data:
            return []
        if self._is_excel(raw_data, filename):
            return self._read_rows_excel(raw_data, filename=filename, limit=limit, offset=offset)
        return self._read_rows_csv(raw_data, limit=limit, offset=offset)

    def _read_rows_excel(self, raw_data, filename="", limit=None, offset=0):
        if openpyxl:
            try:
                return self._read_rows_openpyxl(raw_data, limit=limit, offset=offset)
            except Exception:
                pass

        if xlrd:
            return self._read_rows_xlrd(raw_data, limit=limit, offset=offset)

        raise UserError(_("Neither openpyxl nor xlrd library is installed for Excel reading."))

    def _read_rows_openpyxl(self, raw_data, limit=None, offset=0):
        wb = openpyxl.load_workbook(filename=io.BytesIO(raw_data), read_only=True, data_only=True)
        sheet = wb.active
        headers = []
        rows = []
        current_data_idx = 0

        for idx, row in enumerate(sheet.iter_rows(values_only=True)):
            if idx == 0:
                headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(row)]
                continue
            if current_data_idx < offset:
                current_data_idx += 1
                continue
            if limit is not None and len(rows) >= limit:
                break

            row_dict = {}
            has_data = False
            for col_idx, h in enumerate(headers):
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None and str(val).strip() != "":
                    has_data = True
                row_dict[h] = val if val is not None else ""
            if has_data:
                rows.append((current_data_idx + 1, row_dict))
            current_data_idx += 1

        wb.close()
        return rows

    def _read_rows_xlrd(self, raw_data, limit=None, offset=0):
        book = xlrd.open_workbook(file_contents=raw_data)
        sheet = book.sheet_by_index(0)
        if sheet.nrows == 0:
            return []

        headers = [str(c).strip() if c is not None and str(c).strip() else f"Column_{i+1}" for i, c in enumerate(sheet.row_values(0))]
        rows = []
        current_data_idx = 0

        for rowx in range(1, sheet.nrows):
            if current_data_idx < offset:
                current_data_idx += 1
                continue
            if limit is not None and len(rows) >= limit:
                break

            row_cells = sheet.row(rowx)
            row_dict = {}
            has_data = False

            for colx, h in enumerate(headers):
                if colx >= len(row_cells):
                    row_dict[h] = ""
                    continue
                cell = row_cells[colx]
                val = ""
                if cell.ctype is xlrd.XL_CELL_NUMBER:
                    val = str(cell.value) if cell.value % 1 != 0.0 else str(int(cell.value))
                elif cell.ctype is xlrd.XL_CELL_DATE:
                    try:
                        dt = datetime.datetime(*xlrd.xldate.xldate_as_tuple(cell.value, book.datemode))
                        val = dt.strftime('%Y-%m-%d %H:%M:%S') if cell.value % 1 != 0.0 else dt.strftime('%Y-%m-%d')
                    except Exception:
                        val = str(cell.value)
                elif cell.ctype is xlrd.XL_CELL_BOOLEAN:
                    val = "True" if cell.value else "False"
                elif cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_BLANK):
                    val = str(cell.value).strip()

                if val != "":
                    has_data = True
                row_dict[h] = val

            if has_data:
                rows.append((current_data_idx + 1, row_dict))
            current_data_idx += 1

        return rows

    def _read_rows_csv(self, raw_data, limit=None, offset=0):
        text = self._decode_csv(raw_data)
        sample = text[:4096]
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ',' if ',' in sample else ';'

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        headers = []
        rows = []
        current_data_idx = 0

        for idx, row in enumerate(reader):
            if idx == 0:
                headers = [col.strip() for col in row]
                continue
            if current_data_idx < offset:
                current_data_idx += 1
                continue
            if limit is not None and len(rows) >= limit:
                break

            row_dict = {}
            has_data = False
            for col_idx, h in enumerate(headers):
                val = row[col_idx] if col_idx < len(row) else ""
                if val and str(val).strip() != "":
                    has_data = True
                row_dict[h] = val.strip()
            if has_data:
                rows.append((current_data_idx + 1, row_dict))
            current_data_idx += 1

        return rows

    def get_total_rows(self, raw_data, filename=""):
        if not raw_data:
            return 0
        if self._is_excel(raw_data, filename):
            if openpyxl:
                try:
                    wb = openpyxl.load_workbook(filename=io.BytesIO(raw_data), read_only=True, data_only=True)
                    sheet = wb.active
                    count = max(0, sum(1 for _ in sheet.iter_rows(values_only=True)) - 1)
                    wb.close()
                    return count
                except Exception:
                    pass
            if xlrd:
                book = xlrd.open_workbook(file_contents=raw_data)
                sheet = book.sheet_by_index(0)
                return max(0, sheet.nrows - 1)
            return 0
        else:
            text = self._decode_csv(raw_data)
            lines = text.count('\n')
            return max(0, lines - 1 if text.endswith('\n') else lines)

    def _decode_csv(self, raw_data):
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                return raw_data.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw_data.decode('utf-8', errors='replace')

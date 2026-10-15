"""Bounded read-only CSV/Parquet access through an operator-approved manifest."""

import csv
from datetime import date
import hashlib
import io
import math
import os
from pathlib import Path
import stat

from .contracts import ContractError, fingerprint, object_schema, parse_json, validate
from .security import Denied
from .tools import ToolRegistry, ToolSpec

MAX_BYTES = 4 * 1024 * 1024
RESOURCE_RECORD = object_schema({
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9:_-]{1,60}$"},
    "path": {"type": "string", "minLength": 1},
    "format": {"enum": ["csv", "parquet", "published_npy"]},
    "source": {"type": "string", "minLength": 1, "maxLength": 500},
    "approval_ref": {"type": "string", "minLength": 1, "maxLength": 200},
    "data_kind": {"enum": ["real", "synthetic"]},
    "frequency": {"const": "daily"},
    "timezone": {"type": "string", "minLength": 1, "maxLength": 100},
    "start_date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
    "end_date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
    "date_column": {"type": "string", "minLength": 1, "maxLength": 100},
    "fields": {"type": "object", "minProperties": 1, "maxProperties": 20,
               "additionalProperties": {"enum": ["string", "date", "float", "int", "unknown"]}},
    "adjustment": {"type": "string", "minLength": 1, "maxLength": 200},
    "available_time": {"type": "string", "minLength": 1, "maxLength": 500},
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "partition": {"enum": ["train", "validation"]},
    "release_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
    "access_status": {"enum": ["PROFILED_EXPLORATORY_ONLY", "WITHHELD_LEGACY_2026"]},
}, required=['id','path','format','source','approval_ref','data_kind','frequency','timezone',
             'start_date','end_date','date_column','fields','adjustment','available_time','sha256'])
MANIFEST_SCHEMA = object_schema({"version": {"const": "1"},
    "resources": {"type": "array", "minItems": 1, "maxItems": 8, "items": RESOURCE_RECORD},
    'withheld_from':{'type':'string','pattern':'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'}},required=['version','resources'])
PUBLIC_RECORD = object_schema({k: v for k, v in RESOURCE_RECORD["properties"].items() if k != "path"},
                             required=[k for k in RESOURCE_RECORD['required'] if k!='path'])


class ResourceCatalog:
    def __init__(self, manifest_path):
        self._manifest_path = Path(manifest_path).absolute()
        self._check_path(self._manifest_path)
        if self._manifest_path.stat().st_size > 65536:
            raise Denied("MANIFEST_TOO_LARGE")
        value = parse_json(self._manifest_path.read_text(encoding="utf-8"))
        validate(value, MANIFEST_SCHEMA)
        self.digest = fingerprint(value)
        # A single trusted embargo covers every alias and every Tool using this catalog.
        # It is admission control, not an OS sandbox or a retroactive blind-test claim.
        self.withheld_from = value.get('withheld_from')
        if self.withheld_from:
            date.fromisoformat(self.withheld_from)
        self.records = {}
        self._published_cache = {}
        for record in value["resources"]:
            if self.withheld_from and record['end_date'] >= self.withheld_from and record.get('access_status') != 'WITHHELD_LEGACY_2026':
                raise Denied('HOLDOUT_PUBLICATION_OVERLAP')
            if record["id"] in self.records:
                raise ContractError("duplicate resource id")
            path = Path(record["path"])
            if not path.is_absolute():
                raise Denied("RESOURCE_PATH_MUST_BE_ABSOLUTE")
            self._check_path(path)
            if record["date_column"] not in record["fields"]:
                raise ContractError("date column not declared")
            if date.fromisoformat(record["start_date"]) > date.fromisoformat(record["end_date"]):
                raise ContractError("invalid coverage")
            self.records[record["id"]] = record

    def published(self, resource_id):
        """Only immutable released arrays; the model never supplies a path or budget."""
        import numpy as np
        from .published_release import read, FIELDS, SPLITS, VERSION
        record = self.records.get(resource_id)
        if not record or record.get('access_status') == 'WITHHELD_LEGACY_2026':
            raise Denied('HOLDOUT_DATA_ACCESS_DENIED')
        if record['format'] != 'published_npy':
            raise Denied('NOT_A_PUBLISHED_PARTITION')
        path = Path(record['path']); self._check_path(path)
        if path.stat().st_size > 1024 * 1024:
            raise Denied('RELEASE_MANIFEST_TOO_LARGE')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise Denied('RELEASE_MANIFEST_CHANGED')
        metadata = parse_json(raw.decode('utf-8'), max_bytes=1024*1024)
        split, batch = record.get('partition'), record.get('release_id')
        if (split not in SPLITS or metadata.get('version') != VERSION or metadata.get('split') != split or
            metadata.get('release_id') != batch or path.parent.name != batch or path.parent.parent.name != split or
            metadata.get('parent_id') is not None or metadata.get('status') != 'PROFILED_EXPLORATORY_ONLY'):
            raise Denied('RELEASE_CONTRACT_INVALID')
        dates, codes = metadata['dates'], metadata['codes']
        lo, hi = SPLITS[split]
        import re
        if (not dates or not codes or len(dates) > 1000 or len(codes) > 6000 or
            dates != sorted(set(dates)) or len(set(codes)) != len(codes) or
            any(not isinstance(d,str) or not re.fullmatch(r'\d{8}',d) or not lo <= d <= hi for d in dates) or
            any(not isinstance(c,str) or not re.fullmatch(r'\d{6}\.(SH|SZ)',c) for c in codes) or
            len({c[:6] for c in codes}) != len(codes) or
            dates[0] != record['start_date'].replace('-','') or dates[-1] != record['end_date'].replace('-','')):
            raise Denied('RELEASE_AXES_OR_BOUNDARY_INVALID')
        signatures = []
        for name in FIELDS:
            file = path.parent / (name + '.npy'); self._check_path(file)
            st = file.stat()
            if st.st_size > 64 * 1024 * 1024:
                raise Denied('RELEASE_FILE_BUDGET')
            signatures.append((st.st_ino, st.st_size, st.st_mtime_ns))
        cached = self._published_cache.get(resource_id)
        if cached and cached[0] == signatures:
            return record, cached[1], metadata
        panel = read(path.parent.parent.parent, split, batch, max_cells=36_000_000)
        for name, values in panel.fields.items():
            if values.dtype != np.dtype('float64') or np.isinf(values).any():
                raise Denied('RELEASE_NUMERIC_CONTRACT')
            values.flags.writeable = False
        after = [(p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns)
                 for p in (path.parent / (n+'.npy') for n in FIELDS)]
        if after != signatures:
            raise Denied('RELEASE_CHANGED_DURING_READ')
        self._published_cache[resource_id] = (signatures, panel)
        return record, panel, metadata

    @staticmethod
    def _check_path(path):
        if ".." in path.parts:
            raise Denied("RESOURCE_PATH_TRAVERSAL")
        for part in (path, *path.parents):
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise Denied("RESOURCE_LINK_DENIED")
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
            raise Denied("RESOURCE_FILE_DENIED")

    def _read(self, resource_id):
        if resource_id not in self.records:
            raise Denied("RESOURCE_NOT_REGISTERED")
        record = self.records[resource_id]
        if record.get('access_status') == 'WITHHELD_LEGACY_2026':
            raise Denied('HOLDOUT_DATA_ACCESS_DENIED')
        if record['format'] == 'published_npy':
            raise Denied('PUBLISHED_PARTITION_REQUIRES_BOUNDED_READER')
        path = Path(record["path"])
        self._check_path(path)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
                raise Denied("RESOURCE_SIZE_OR_TYPE_DENIED")
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise Denied("RESOURCE_CHANGED_DURING_READ")
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise Denied("RESOURCE_FINGERPRINT_MISMATCH")
        if record["format"] == "csv":
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            names = reader.fieldnames or []
            if set(names) != set(record["fields"]) or len(names) != len(set(names)):
                raise ContractError("CSV fields differ from approved manifest")
            rows = []
            for row in reader:
                if None in row or len(rows) >= 10000:
                    raise Denied("RESOURCE_ROW_LIMIT_OR_SCHEMA")
                rows.append(row)
        else:
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError:
                raise Denied("PARQUET_DEPENDENCY_MISSING") from None
            parquet = pq.ParquetFile(pa.BufferReader(raw))
            if parquet.metadata.num_rows > 10000 or parquet.metadata.num_columns > 20 or sum(
                    parquet.metadata.row_group(i).total_byte_size for i in range(parquet.metadata.num_row_groups)) > MAX_BYTES * 8:
                raise Denied("PARQUET_EXPANSION_LIMIT")
            if set(parquet.schema_arrow.names) != set(record["fields"]):
                raise ContractError("Parquet fields differ from approved manifest")
            rows = parquet.read(columns=list(record["fields"])).to_pylist()
        normalized = []
        for row in rows:
            out = {}
            for name, kind in record["fields"].items():
                value = row.get(name)
                if value is None or value == "":
                    out[name] = None
                elif kind in {"float", "int"}:
                    number = float(value)
                    if not math.isfinite(number) or kind == "int" and not number.is_integer():
                        raise ContractError("invalid numeric data")
                    out[name] = int(number) if kind == "int" else number
                elif kind == "date":
                    out[name] = date.fromisoformat(str(value)).isoformat()
                else:
                    text = str(value)
                    if len(text) > 256:
                        raise Denied("DATA_CELL_TOO_LARGE")
                    out[name] = text
            d = date.fromisoformat(str(out[record["date_column"]]))
            if self.withheld_from and d.isoformat() >= self.withheld_from:
                raise Denied('HOLDOUT_DATA_ACCESS_DENIED')
            if not record["start_date"] <= d.isoformat() <= record["end_date"]:
                raise ContractError("data outside approved coverage")
            normalized.append(out)
        return record, normalized

    def list_resources(self):
        return {"mode": "catalog", "manifest_sha256": self.digest,
                "resources": [{k: v for k, v in x.items() if k != "path"} for x in self.records.values()]}

    def describe_resource(self, resource_id):
        if self.records.get(resource_id, {}).get('format') == 'published_npy':
            import numpy as np
            record, panel, _ = self.published(resource_id)
            return dict(mode='real_data',resource_id=resource_id,data_sha256=record['sha256'],
                metadata={k:v for k,v in record.items() if k!='path'},row_count=len(panel.dates)*len(panel.codes),
                observed_start=record['start_date'],observed_end=record['end_date'],
                null_counts={k:int(np.isnan(v).sum()) for k,v in panel.fields.items()},formal_backtest_ready=False)
        record, rows = self._read(resource_id)
        return {"mode": "real_data" if record["data_kind"] == "real" else "synthetic",
                "resource_id": resource_id, "data_sha256": record["sha256"],
                "metadata": {k: v for k, v in record.items() if k != "path"}, "row_count": len(rows),
                "observed_start": min((x[record["date_column"]] for x in rows), default=None),
                "observed_end": max((x[record["date_column"]] for x in rows), default=None),
                "null_counts": {k: sum(x[k] is None for x in rows) for k in record["fields"]},
                "formal_backtest_ready": False}

    def read_data_slice(self, resource_id, fields, start_date, end_date, limit):
        record = self.records.get(resource_id)
        if record is None or any(x not in record["fields"] for x in fields):
            raise Denied("FIELD_OR_RESOURCE_NOT_AUTHORIZED")
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if start > end or start_date < record["start_date"] or end_date > record["end_date"]:
            raise Denied("DATE_RANGE_NOT_AUTHORIZED")
        if record['format'] == 'published_npy':
            record, panel, _ = self.published(resource_id)
            selected = [i for i,d in enumerate(panel.dates) if start_date.replace('-','') <= d <= end_date.replace('-','')]
            rows = []
            for i in selected:
                for j, code in enumerate(panel.codes):
                    row = {}
                    for field in fields:
                        value = panel.dates[i][:4]+'-'+panel.dates[i][4:6]+'-'+panel.dates[i][6:] if field=='date' else code if field=='code' else float(panel.fields[field][i,j])
                        row[field] = None if isinstance(value,float) and not math.isfinite(value) else value
                    rows.append(row)
                    if len(rows) == limit: break
                if len(rows) == limit: break
            return dict(mode='real_data',resource_id=resource_id,data_sha256=record['sha256'],fields=fields,rows=rows,
                row_count=len(rows),truncated=len(selected)*len(panel.codes)>limit,quality_scope='descriptive_only',formal_backtest_ready=False)
        record, rows = self._read(resource_id)
        selected = [x for x in rows if start_date <= x[record["date_column"]] <= end_date]
        return {"mode": "real_data" if record["data_kind"] == "real" else "synthetic",
                "resource_id": resource_id, "data_sha256": record["sha256"], "fields": fields,
                "rows": [{k: x[k] for k in fields} for x in selected[:limit]],
                "row_count": min(limit, len(selected)), "truncated": len(selected) > limit,
                "quality_scope": "descriptive_only", "formal_backtest_ready": False}

    def registry(self):
        resource = {"type": "string", "enum": list(self.records)}
        date_field = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
        mode = {"enum": ["real_data", "synthetic"]}
        digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
        common = {"mode": mode, "resource_id": resource, "data_sha256": digest}
        list_output = object_schema({"mode": {"const": "catalog"}, "manifest_sha256": digest,
            "resources": {"type": "array", "minItems": 1, "maxItems": 8, "items": PUBLIC_RECORD}})
        describe_output = object_schema({**common, "metadata": PUBLIC_RECORD,
            "row_count": {"type": "integer", "minimum": 0, "maximum": 6000000},
            "observed_start": {"type": ["string", "null"]}, "observed_end": {"type": ["string", "null"]},
            "null_counts": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
            "formal_backtest_ready": {"const": False}})
        slice_output = object_schema({**common, "fields": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "maxItems": 200, "items": {"type": "object",
                "additionalProperties": {"type": ["string", "number", "null"]}}},
            "row_count": {"type": "integer", "minimum": 0, "maximum": 200}, "truncated": {"type": "boolean"},
            "quality_scope": {"const": "descriptive_only"}, "formal_backtest_ready": {"const": False}})
        return ToolRegistry([
            ToolSpec("list_resources", "1.0.0", "列出本任务已授权日频资源的来源、字段和口径；不返回文件路径。",
                     object_schema({}), list_output, self.list_resources, kind="data_readonly", resource_mode="catalog"),
            ToolSpec("describe_resource", "1.0.0", "只读核验小资源指纹、字段、实际日期和缺失计数；不产生回测结论。",
                     object_schema({"resource_id": resource}), describe_output, self.describe_resource, kind="data_readonly"),
            ToolSpec("read_data_slice", "1.0.0", "读取已授权小资源切片；最多200行；不得传入路径或代码。",
                     object_schema({"resource_id": resource, "fields": {"type": "array", "minItems": 1, "maxItems": 20,
                         "uniqueItems": True, "items": {"type": "string", "enum": sorted({f for r in self.records.values() for f in r["fields"]})}},
                         "start_date": date_field, "end_date": date_field,
                         "limit": {"type": "integer", "minimum": 1, "maximum": 200}}), slice_output, self.read_data_slice, kind="data_readonly"),
        ], context={"resource_manifest_sha256": self.digest})

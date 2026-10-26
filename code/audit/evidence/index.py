"""Build (once) and query the evidence index shared by every case."""
from __future__ import annotations

import re
from collections import defaultdict

from ..common import DATASET, RES_RE
from ..loaders import load_activity, load_manifest
from . import docs, logsrc, recsrc, sqlsrc
from .obs import Coverage, Ids, Obs, collect_ids, make_obs

LINK_RE = re.compile(r"linked (\S+) \((.+?)\) to (\S+@\S+) and (user_\d+)")
LINK_RE2 = re.compile(r"confirmed (\S+) \((.+?)\) belongs only to (\S+@\S+) and (user_\d+)")


class EvidenceIndex:
    def __init__(self):
        self.manifest = {r["file_id"]: r for r in load_manifest()}
        self.activity = load_activity()
        self.obs: list[Obs] = []
        self.coverage: list[Coverage] = []
        self.aliases: dict[str, str] = {}        # printed label -> resource_id
        self.links: list[tuple] = []             # (activity_id, time, resource, email, user)
        self._read_links()
        self._parse_files()
        self.by_resource: dict[str, list[Obs]] = defaultdict(list)
        for o in self.obs:
            if o.resource_id:
                self.by_resource[o.resource_id].append(o)

    def _read_links(self) -> None:
        for a in self.activity:
            if a["event_type"] != "LINK_RESOURCE_IDENTITY":
                continue
            m = LINK_RE.search(a["details"]) or LINK_RE2.search(a["details"])
            if not m:
                continue
            rid, label, email, user = m.groups()
            self.aliases[label] = rid
            self.links.append((a["activity_id"], a["event_time"], rid, email.rstrip(".").lower(), user))

    def _parse_files(self) -> None:
        for fid, row in self.manifest.items():
            path = DATASET / row["file_path"]
            ft = row["captured_at"]
            ext = path.suffix.lower()
            if ext == ".sql":
                obs, cov = sqlsrc.parse_sql(path, fid, ft)
            elif ext == ".json":
                obs, cov = recsrc.parse_json(path, fid, ft)
            elif ext == ".txt":
                obs, cov = recsrc.parse_txt(path, fid, ft)
            elif ext == ".log":
                obs, cov = logsrc.parse_log(path, fid, ft)
            elif ext in (".png", ".pdf"):
                obs, cov = docs.parse_cached(fid, ft, self.aliases)
            else:
                continue
            self.obs.extend(obs)
            self.coverage.extend(cov)

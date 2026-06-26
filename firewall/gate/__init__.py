"""L0 static gate.

Two complementary scanners:

* :mod:`firewall.gate.static_scanner` — built-in lightweight static checks
  (hidden frontmatter content, suspicious endpoints, bundled artifacts).
* ``firewall.gate.cisco_scan`` (shell wrapper) — optional integration
  with the external ``cisco-ai-skill-scanner`` pip package.

Both emit :class:`Finding` records; the install policy
(``prescan``: only CRITICAL hard-blocks) is enforced by the L2 layer,
not here. See ``firewall.runtime.firewall`` invariants (2) and (3).
"""

from firewall.gate.static_scanner import Finding, scan_skill_dir

__all__ = ["Finding", "scan_skill_dir"]

# Third-Party Notices

This project incorporates source code from the following third-party projects.

## OpenMW

`native/third_party/openmw_nif/` contains a verbatim mirror of the NIF parser
from [OpenMW](https://openmw.org/), specifically the `components/nif/`
directory. OpenMW is licensed under the GNU General Public License version 3
(GPLv3), the same license as open_stbc. Original file headers are preserved
in the mirrored source. The full OpenMW LICENSE is reproduced at
`native/third_party/openmw_nif/LICENSE`. Upstream commit SHA is recorded in
`native/third_party/openmw_nif/UPSTREAM_VERSION`.

## NifSkope

[NifSkope](https://github.com/niftools/nifskope) is used as a reference for
the NIF binary format. Its `nif.xml` schema documents block layouts. NifSkope
itself is **not** incorporated into open_stbc — it is reference documentation
only. NifSkope is licensed under a BSD-style license; see
https://github.com/niftools/nifskope/blob/develop/LICENSE.md.

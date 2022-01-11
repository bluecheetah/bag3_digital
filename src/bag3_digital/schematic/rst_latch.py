# SPDX-License-Identifier: BSD-3-Clause AND Apache-2.0
# Copyright 2018 Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Copyright 2019 Blue Cheetah Analog Design Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Mapping, Any, Union

import pkg_resources
from pathlib import Path

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param

from ..layout.stdcells.util import RstType


# noinspection PyPep8Naming
class bag3_digital__rst_latch(Module):
    """Module for library bag3_digital cell rst_latch.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'rst_latch.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Mapping[str, str]:
        return dict(
            tin='Input tristate inverter params',
            tfb='Feedback (keeper) tristate inverter params',
            nor='Output Nor params',
            rst_type='SET or RESET; RESET by default',
        )

    @classmethod
    def get_default_param_values(cls) -> Mapping[str, Any]:
        return dict(rst_type=RstType.RESET)

    def get_master_basename(self) -> str:
        rst_type: Union[str, RstType] = self.params['rst_type']
        if isinstance(rst_type, str):
            rst_type = RstType[rst_type]
        if rst_type is RstType.SET:
            return 'set_latch'
        return 'rst_latch'

    def design(self, tin: Mapping[str, Any], tfb: Mapping[str, Any], nor: Mapping[str, Any],
               rst_type: Union[str, RstType]) -> None:
        self.instances['XTBUF'].design(**tin)
        self.instances['XTFB'].design(**tfb)
        self.instances['XCM'].design(nin=2)

        if isinstance(rst_type, str):
            rst_type = RstType[rst_type]
        if rst_type is RstType.SET:
            self.replace_instance_master('XNOR', 'bag3_digital', 'nand', keep_connections=True)
            self.rename_instance('XNOR', 'XNAND', [(f'in<1:0>', 'outb,setb')])
            self.instances['XNAND'].design(**nor)
            self.rename_pin('rst', 'setb')
        else:
            self.instances['XNOR'].design(**nor)

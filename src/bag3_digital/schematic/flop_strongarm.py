# SPDX-License-Identifier: Apache-2.0
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

# -*- coding: utf-8 -*-

from typing import Dict, Any, Optional

import pkg_resources
from pathlib import Path

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
class bag3_digital__flop_strongarm(Module):
    """Module for library bag3_digital cell flop_strongarm.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                str(Path('netlist_info',
                                                         'flop_strongarm.yaml')))

    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            sa_params='strongarm frontend parameters.',
            sr_params='sr latch parameters.',
            midbuf_params='Optional buffer parameters for output of the strongarm frontend',
            dum_buf_params='Optional dummy buffer parameters',
            has_rstlb='True to add rstlb functionality.',
            export_mid='True to export intermediate nodes',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(has_rstlb=False, export_mid=False, midbuf_params=None, dum_buf_params=None)

    def design(self, sa_params: Param, sr_params: Param, midbuf_params: Optional[Param],
               dum_buf_params: Optional[Param], has_rstlb: bool, export_mid: bool) -> None:
        if midbuf_params is None:
            self.remove_instance('XMBUF<1:0>')
            self.reconnect_instance('XSR', {'sb': 'midn', 'rb': 'midp'}.items())
            needs_inbuf = True
            nets_to_export = []
        else:
            self.instances['XMBUF<1:0>'].design(**midbuf_params)
            midbuf_master: Module = self.instances['XMBUF<1:0>'].master
            num_stg = len(midbuf_master.params['inv_params'])
            dual_out = midbuf_master.params['dual_output']
            needs_inbuf = num_stg == 1 or not dual_out
            nets_to_export = ['midp_buf', 'midn_buf']
            if needs_inbuf and num_stg % 2 == 1:
                raise ValueError("Mid buffer must have an even number of stages if SR latch input buffer is required")
            if dual_out:
                self.reconnect_instance('XSR', {'s': 'midn_bufb', 'r': 'midp_bufb'}.items())
                nets_to_export.extend(['midp_bufb', 'midn_bufb'])

        if dum_buf_params is None:
            self.remove_instance('XDUM')
        else:
            self.instances['XDUM'].design(**dum_buf_params)

        inbuf_test = sr_params.get('inbuf_params', None)
        if needs_inbuf and inbuf_test is None:
            raise ValueError('SR latch must have input buffers.')
        
        self.instances['XSA'].design(has_rstb=has_rstlb, **sa_params.copy(append=dict(export_mid=export_mid)))
        self.instances['XSR'].design(has_rstb=has_rstlb, **sr_params)

        if not has_rstlb:
            self.remove_pin('rstlb')

        if export_mid:
            self.add_pin('midp', TermType.inout)
            self.add_pin('midn', TermType.inout)

            for net in nets_to_export:
                self.add_pin(net, TermType.inout)

            sa_debug_conns = {pin: f'fe_{pin}' for pin in ['midp', 'midn', 'tail']}
            self.reconnect_instance('XSA', sa_debug_conns.items())
            for pin in sa_debug_conns.values():
                self.add_pin(pin, TermType.inout)

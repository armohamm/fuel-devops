# -*- coding: utf-8 -*-

#    Copyright 2015 - 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# pylint: disable=no-self-use

import unittest

import mock

from devops import error
from devops.helpers import ntp
from devops.helpers import ssh_client


class NtpTestCase(unittest.TestCase):

    def patch(self, *args, **kwargs):
        patcher = mock.patch(*args, **kwargs)
        m = patcher.start()
        self.addCleanup(patcher.stop)
        return m

    def setUp(self):
        self.remote_mock = mock.Mock(spec=ssh_client.SSHClient)
        self.remote_mock.__repr__ = mock.Mock(return_value='<SSHClient()>')

        self.wait_mock = self.patch('devops.helpers.helpers.wait')

    @staticmethod
    def make_exec_result(stdout, exit_code=0):
        return {
            'exit_code': exit_code,
            'stderr': [],
            'stdout': stdout.splitlines(True),
        }


class TestNtpInitscript(NtpTestCase):

    def setUp(self):
        super(TestNtpInitscript, self).setUp()

        self.remote_mock.execute.return_value = self.make_exec_result(
            '/etc/init.d/ntp')

    def test_init(self):
        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        assert ntp_init.remote is self.remote_mock
        assert ntp_init.node_name == 'node'
        assert repr(ntp_init) == \
            "NtpInitscript(remote=<SSHClient()>, node_name='node')"
        self.remote_mock.execute.assert_called_once_with(
            "find /etc/init.d/ -regex '/etc/init.d/ntp.?' -executable")

    def test_start(self):
        self.remote_mock.check_call.return_value = self.make_exec_result('')

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        ntp_init.start()

        self.remote_mock.check_call.assert_called_once_with(
            '/etc/init.d/ntp start')

    def test_stop(self):
        self.remote_mock.check_call.return_value = self.make_exec_result('')

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        ntp_init.stop()

        self.remote_mock.check_call.assert_called_once_with(
            '/etc/init.d/ntp stop')

    def test_get_ntpq(self):
        self.remote_mock.execute.side_effect = (
            self.make_exec_result('/etc/init.d/ntp'),
            self.make_exec_result('Line1\nLine2\nLine3\nLine4\n'),
        )

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        peers = ntp_init._get_ntpq()

        self.remote_mock.execute.assert_has_calls((
            mock.call(
                "find /etc/init.d/ -regex '/etc/init.d/ntp.?' -executable"),
            mock.call('ntpq -pn 127.0.0.1'),
        ))
        assert peers == ['Line3\n', 'Line4\n']

    def test_date(self):
        self.remote_mock.execute.side_effect = (
            self.make_exec_result('/etc/init.d/ntp'),
            self.make_exec_result('Thu May 26 13:35:43 MSK 2016'),
        )

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        date = ntp_init.date

        self.remote_mock.execute.assert_has_calls((
            mock.call(
                "find /etc/init.d/ -regex '/etc/init.d/ntp.?' -executable"),
            mock.call('date'),
        ))
        assert date == 'Thu May 26 13:35:43 MSK 2016'

    def test_set_actual_time(self):
        self.remote_mock.execute.side_effect = (
            self.make_exec_result('/etc/init.d/ntp'),
            self.make_exec_result('server1.com'),
            self.make_exec_result(''),
        )

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        ntp_init.set_actual_time()

        self.wait_mock.assert_called_once_with(
            mock.ANY, timeout=600,
            timeout_msg="Failed to set actual time on node 'node'")

        waiter = self.wait_mock.call_args[0][0]
        assert waiter() is True
        self.remote_mock.execute.assert_has_calls((
            mock.call(
                "find /etc/init.d/ -regex '/etc/init.d/ntp.?' -executable"),
            mock.call('ntpd -gqd'),
        ))

        self.remote_mock.check_call.assert_called_once_with('hwclock -w')

    def test_get_sync_complete(self):
        self.remote_mock.execute.side_effect = (
            self.make_exec_result('/etc/init.d/ntp'),
            self.make_exec_result("""\
     remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
-95.213.132.250  195.210.189.106  2 u    8   64  377   40.263   -1.379  15.326
*87.229.205.75   212.51.144.44    2 u   16   64  377   31.288   -1.919   9.969
+31.131.249.26   46.46.152.214    2 u   34   64  377   40.522   -0.988   7.747
-217.65.8.75     195.3.254.2      3 u   26   64  377   28.758   -4.249  44.240
+91.189.94.4     138.96.64.10     2 u   24   64  377   83.284   -1.810  14.550
"""))

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        assert ntp_init._get_sync_complete() is True

    def test_get_sync_complete_with_unstable_peer(self):
        self.remote_mock.execute.side_effect = (
            self.make_exec_result('/etc/init.d/ntp'),
            self.make_exec_result("""\
     remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
+95.213.132.250  195.210.189.106  2 u    8   64  377   40.263   -1.379  532.46
-87.229.205.75   212.51.144.44    2 u   16   64  377   31.288   -1.919   9.969
*31.131.249.26   46.46.152.214    2 u   34   64    1   40.522   -0.988   7.747
-217.65.8.75     195.3.254.2      3 u   26   64  377   28.758   -4.249  44.240
+91.189.94.4     138.96.64.10     2 u   24   64  377   83.284   -1.810  14.550
"""))

        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        assert ntp_init._get_sync_complete() is True

    def test_wait_peer(self):
        ntp_init = ntp.NtpInitscript(self.remote_mock, 'node')
        ntp_init.wait_peer()

        self.wait_mock.assert_called_once_with(
            ntp_init._get_sync_complete, interval=8, timeout=600,
            timeout_msg="Failed to wait peer on node 'node'")


class TestNtpPacemaker(NtpTestCase):

    def test_init(self):
        ntp_pcm = ntp.NtpPacemaker(self.remote_mock, 'node')
        assert ntp_pcm.remote is self.remote_mock
        assert ntp_pcm.node_name == 'node'
        assert repr(ntp_pcm) == \
            "NtpPacemaker(remote=<SSHClient()>, node_name='node')"

    def test_start(self):
        ntp_pcm = ntp.NtpPacemaker(self.remote_mock, 'node')
        ntp_pcm.start()

        self.remote_mock.execute.assert_has_calls((
            mock.call('ip netns exec vrouter ip l set dev lo up'),
            mock.call('crm resource start p_ntp'),
        ))

    def test_stop(self):
        ntp_pcm = ntp.NtpPacemaker(self.remote_mock, 'node')
        ntp_pcm.stop()

        self.remote_mock.execute.assert_called_once_with(
            'crm resource stop p_ntp; killall ntpd')

    def test_get_ntpq(self):
        self.remote_mock.execute.return_value = self.make_exec_result(
            'Line1\nLine2\nLine3\nLine4\n')

        ntp_pcm = ntp.NtpPacemaker(self.remote_mock, 'node')
        peers = ntp_pcm._get_ntpq()

        self.remote_mock.execute.assert_called_once_with(
            'ip netns exec vrouter ntpq -pn 127.0.0.1')
        assert peers == ['Line3\n', 'Line4\n']


class TestNtpSystemd(NtpTestCase):

    def test_init(self):
        ntp_sysd = ntp.NtpSystemd(self.remote_mock, 'node')
        assert ntp_sysd.remote is self.remote_mock
        assert ntp_sysd.node_name == 'node'
        assert repr(ntp_sysd) == \
            "NtpSystemd(remote=<SSHClient()>, node_name='node')"

    def test_start(self):
        ntp_sysd = ntp.NtpSystemd(self.remote_mock, 'node')
        ntp_sysd.start()

        self.remote_mock.check_call.assert_called_once_with(
            'systemctl start ntpd')

    def test_stop(self):
        ntp_sysd = ntp.NtpSystemd(self.remote_mock, 'node')
        ntp_sysd.stop()

        self.remote_mock.check_call.assert_called_once_with(
            'systemctl stop ntpd')


class TestNtpChronyd(NtpTestCase):

    def test_init(self):
        ntp_chrony = ntp.NtpChronyd(self.remote_mock, 'node')
        assert ntp_chrony.remote is self.remote_mock
        assert ntp_chrony.node_name == 'node'
        assert repr(ntp_chrony) == \
            "NtpChronyd(remote=<SSHClient()>, node_name='node')"

        ntp_chrony.start()
        ntp_chrony.stop()

    def test_get_burst_complete(self):
        self.remote_mock.check_call.return_value = \
            self.make_exec_result("""200 OK
200 OK
4 sources online
0 sources offline
0 sources doing burst (return to online)
0 sources doing burst (return to offline)
0 sources with unknown address""")

        ntp_chrony = ntp.NtpChronyd(self.remote_mock, 'node')
        r = ntp_chrony._get_burst_complete()
        self.remote_mock.check_call.assert_called_once_with(
            'chronyc -a activity')
        assert r is True

    def test_get_burst_complete_false(self):
        self.remote_mock.check_call.return_value = \
            self.make_exec_result("""200 OK
200 OK
3 sources online
0 sources offline
1 sources doing burst (return to online)
0 sources doing burst (return to offline)
0 sources with unknown address""")

        ntp_chrony = ntp.NtpChronyd(self.remote_mock, 'node')
        r = ntp_chrony._get_burst_complete()
        self.remote_mock.check_call.assert_called_once_with(
            'chronyc -a activity')
        assert r is False

    def test_set_actual_time(self):
        ntp_chrony = ntp.NtpChronyd(self.remote_mock, 'node')
        ntp_chrony.set_actual_time()
        self.remote_mock.check_call.assert_has_calls((
            mock.call('chronyc -a burst 3/5'),
            mock.call('chronyc -a makestep'),
        ))
        self.wait_mock.assert_called_once_with(
            ntp_chrony._get_burst_complete, timeout=600,
            timeout_msg="Failed to set actual time on node 'node'")

    def test_wait_peer(self):
        ntp_chrony = ntp.NtpChronyd(self.remote_mock, 'node')
        ntp_chrony.wait_peer()
        self.remote_mock.check_call.assert_called_once_with(
            'chronyc -a waitsync 10 0.01')


class GroupNtpSync(NtpTestCase):

    def setUp(self):
        super(GroupNtpSync, self).setUp()
        self.exec_results = {}
        bad_result = self.make_exec_result('', -1)
        self.remote_mock.execute.side_effect = \
            lambda cmd: self.exec_results.get(cmd, bad_result)

    def test_get_ntp_error(self):
        with self.assertRaises(error.DevopsError):
            ntp.GroupNtpSync.get_ntp(self.remote_mock, 'node1')

    def test_get_ntp_pcs(self):
        pcs_cmd = "ps -C pacemakerd && crm_resource --resource p_ntp --locate"
        self.exec_results[pcs_cmd] = self.make_exec_result('')

        pcs_ntp = ntp.GroupNtpSync.get_ntp(self.remote_mock, 'node1')
        assert isinstance(pcs_ntp, ntp.NtpPacemaker)
        assert pcs_ntp.remote is self.remote_mock
        assert pcs_ntp.node_name == 'node1'

    def test_get_ntp_systemd(self):
        systemd_cmd = "systemctl list-unit-files| grep ntpd"
        self.exec_results[systemd_cmd] = self.make_exec_result('')

        systemd_ntp = ntp.GroupNtpSync.get_ntp(self.remote_mock, 'node1')
        assert isinstance(systemd_ntp, ntp.NtpSystemd)
        assert systemd_ntp.remote is self.remote_mock
        assert systemd_ntp.node_name == 'node1'

    def test_get_ntp_chronyd(self):
        chronyd_cmd = "systemctl is-active chronyd"
        self.exec_results[chronyd_cmd] = self.make_exec_result('')

        chronyd_ntp = ntp.GroupNtpSync.get_ntp(self.remote_mock, 'node1')
        assert isinstance(chronyd_ntp, ntp.NtpChronyd)
        assert chronyd_ntp.remote is self.remote_mock
        assert chronyd_ntp.node_name == 'node1'

    def test_get_ntp_initd(self):
        initd_cmd = "find /etc/init.d/ -regex '/etc/init.d/ntp.?' -executable"
        self.exec_results[initd_cmd] = self.make_exec_result('/etc/init.d/ntp')

        initd_ntp = ntp.GroupNtpSync.get_ntp(self.remote_mock, 'node1')
        assert isinstance(initd_ntp, ntp.NtpInitscript)
        assert initd_ntp.remote is self.remote_mock
        assert initd_ntp.node_name == 'node1'

    def test_get_curr_time(self):
        pcs_cmd = "ps -C pacemakerd && crm_resource --resource p_ntp --locate"
        self.exec_results[pcs_cmd] = self.make_exec_result('')
        self.exec_results['date'] = self.make_exec_result(
            'Fri Jul 22 12:45:42 MSK 2016')

        group = ntp.GroupNtpSync()
        group.add_node(self.remote_mock, 'node1')
        assert len(group.ntp_groups['pacemaker']) == 1
        assert group.get_curr_time() == {
            'node1': 'Fri Jul 22 12:45:42 MSK 2016'}

    def test_add_node(self):
        pcs_cmd = "ps -C pacemakerd && crm_resource --resource p_ntp --locate"
        self.exec_results[pcs_cmd] = self.make_exec_result('')
        self.exec_results['date'] = self.make_exec_result(
            'Fri Jul 22 12:45:42 MSK 2016')

        group = ntp.GroupNtpSync()
        group.add_node(self.remote_mock, 'node1')
        assert len(group.ntp_groups['admin']) == 0
        assert len(group.ntp_groups['pacemaker']) == 1
        assert len(group.ntp_groups['other']) == 0
        group.add_node(self.remote_mock, 'admin')
        assert len(group.ntp_groups['admin']) == 1
        assert len(group.ntp_groups['pacemaker']) == 1
        assert len(group.ntp_groups['other']) == 0

        chronyd_cmd = "systemctl is-active chronyd"
        del self.exec_results[pcs_cmd]
        self.exec_results[chronyd_cmd] = self.make_exec_result('')

        group.add_node(self.remote_mock, 'node2')
        assert len(group.ntp_groups['admin']) == 1
        assert len(group.ntp_groups['pacemaker']) == 1
        assert len(group.ntp_groups['other']) == 1

        assert group.get_curr_time() == {
            'admin': 'Fri Jul 22 12:45:42 MSK 2016',
            'node1': 'Fri Jul 22 12:45:42 MSK 2016',
            'node2': 'Fri Jul 22 12:45:42 MSK 2016'}

    @mock.patch('devops.helpers.ntp.GroupNtpSync.get_ntp')
    def test_sync_time(self, get_ntp_mock):
        spec = mock.create_autospec(spec=ntp.NtpPacemaker, instance=True)
        admin_ntp_mock = mock.Mock(spec=spec)
        node1_ntp_mock = mock.Mock(spec=spec)
        node2_ntp_mock = mock.Mock(spec=spec)
        get_ntp_mock.side_effect = (
            admin_ntp_mock, node1_ntp_mock, node2_ntp_mock)

        group = ntp.GroupNtpSync()
        group.sync_time('admin')

        group.add_node(self.remote_mock, 'admin')
        group.add_node(self.remote_mock, 'node1')
        group.add_node(self.remote_mock, 'node2')
        assert group.ntp_groups == {
            'admin': [admin_ntp_mock],
            'pacemaker': [node1_ntp_mock, node2_ntp_mock]
        }

        group.sync_time('admin')
        admin_ntp_mock.assert_has_calls((
            mock.call.stop(),
            mock.call.set_actual_time(),
            mock.call.start(),
            mock.call.wait_peer()
        ), any_order=True)
        node1_ntp_mock.stop.assert_not_called()
        node1_ntp_mock.set_actual_time.assert_not_called()
        node1_ntp_mock.start.assert_not_called()
        node1_ntp_mock.wait_peer.assert_not_called()
        node2_ntp_mock.stop.assert_not_called()
        node2_ntp_mock.set_actual_time.assert_not_called()
        node2_ntp_mock.start.assert_not_called()
        node2_ntp_mock.wait_peer.assert_not_called()

        group.sync_time('pacemaker')
        node1_ntp_mock.assert_has_calls((
            mock.call.stop(),
            mock.call.set_actual_time(),
            mock.call.start(),
            mock.call.wait_peer()
        ))
        node2_ntp_mock.assert_has_calls([
            mock.call.stop(),
            mock.call.set_actual_time(),
            mock.call.start(),
            mock.call.wait_peer()
        ])

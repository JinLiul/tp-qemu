import re
import logging


from virttest import error_context
from provider.in_place_upgrade_base import IpuTest

LOG_JOB = logging.getLogger('avocado.test')


class IpuLegacyTest(IpuTest):
    """
    Provide basic functions for in place upgrade test cases

    """

    def __init__(self, test, params):

        super(IpuLegacyTest, self).__init__(test, params)
        self.session = None
        self.test = test
        self.params = params

    def pre_upgrade_whitelist(self, test):
        """
        Fix known issues before executing pre-upgrade

        """
        try:
            # Possible problems with remote login using root account
            self.session.cmd(self.params.get("fix_permit"))
            # Answer file missing will be fixed
            fix_answer = self.params.get("fix_answer_file")
            self.session.cmd(fix_answer, timeout=1200)
            fix_answer_sec = self.params.get("fix_answer_section")
            self.session.cmd(fix_answer_sec, timeout=1200)
            erase_old_kernel = self.params.get("clean_up_old_kernel")
            s, output = self.session.cmd_status_output(erase_old_kernel,
                                                       timeout=1200)
            error_info = self.params.get("error_info")
            if re.search(error_info, output):
                pass
        except Exception as info:
            test.fail("Failed to fix known issues in advance :%s" % str(info))


@error_context.context_aware
def run(test, params, env):
    """
    Run in place upgrade cases rhel7.9 guest:
    a) without RHSM
    1.configure vm
    2.install leapp tool
    3.download new rhel content repo
    4.pre_upgrade test in the vm
    5.upgrade test in the vm
    6.check if it's target system

    b) with rhsm
    1.configure vm
    2.install leapp tool
    3.subscribe vm
    4.pre_upgrade test in the vm
    5.upgrade test in the vm
    6.check if it's target system

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    upgrade_test = IpuLegacyTest(test, params)
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    login_timeout = int(params.get("login_timeout", 360))
    upgrade_test.session = vm.wait_for_login(timeout=login_timeout)
    try:
        # set post_release
        pre_release = params.get("pre_release")
        release_chk = params.get("release_check")
        if pre_release not in upgrade_test.run_guest_cmd(release_chk):
            test.cancel("your image is not for rhel 7.9 product, please check")
        post_release = params.get("post_release")
        if params.get("rhsm_type") == "no_rhsm":
            # internal repo for doing yum update
            # please specify the old_custom_internal_repo_7
            # in the cfg in advance this parameter should
            # contain the repo files, by which you can upgrade
            # old system to the newer version before you do in place upgade
            old_custom_repo = params.get("old_custom_internal_repo_7")
            upgrade_test.yum_update_no_rhsm(test, old_custom_repo)
        elif params.get("rhsm_type") == "rhsm":
            # doing rhsm and update the old system
            # prepare_env, get_answer_files_source and get_answer_files
            # download and use private script to prepare test env
            upgrade_test.run_guest_cmd(params.get("prepare_env"))
            upgrade_test.run_guest_cmd(params.get("get_answer_files_source"))
            upgrade_test.rhsm(test)
        upgrade_test.session = vm.reboot(upgrade_test.session)
        # repo_leapp_7 it's leapp tool's repo
        # repo_leppp_7_seed and ins_leapp_cmd, install leapp tool command
        upgrade_test.run_guest_cmd(params.get("repo_leapp_7"))
        upgrade_test.run_guest_cmd(params.get("repo_leppp_7_seed"))
        upgrade_test.run_guest_cmd(params.get("ins_leapp_cmd_7"))
        if params.get("rhsm_type") == "rhsm":
            upgrade_test.run_guest_cmd(params.get("get_answer_files_source"))
            upgrade_test.run_guest_cmd(params.get("get_answer_files"))
        elif params.get("rhsm_type") == "no_rhsm":
            upgrade_test.run_guest_cmd(params.get("prepare_env"))
            upgrade_test.run_guest_cmd(params.get("get_answer_files_source"))
            upgrade_test.run_guest_cmd(params.get("get_answer_files"))
            # get_custom_7 and export_type_7, set env for no_rhsm test
            upgrade_test.run_guest_cmd(params.get("get_custom_7"))
            upgrade_test.run_guest_cmd(params.get("export_type_7"))
            # please specify the new_rhel_content_7 in the cfg in advance
            # this parameter should contain your upgraded system's repo files
            upgrade_test.run_guest_cmd(params.get("new_rhel_content_7"))
        upgrade_test.pre_upgrade_whitelist(test)
        if params.get("rhsm_type") == "no_rhsm":
            # do preugprade test without rhsm
            upgrade_test.run_guest_cmd(params.get("pre_upgrade_no_rhsm"))
            # do upgrade test without rhsm
            upgrade_test.upgrade_process(params.get("process_upgrade_no_rhsm"))
        elif params.get("rhsm_type") == "rhsm":
            # if you want to use the below method to get answer files
            # please disable "get_answer_files_source" and "get_answer_files"
            # two steps above and run the following two commented steps
            # upgrade_test.run_guest_cmd(params.get("leapp_proxy_host"))
            # upgrade_test.run_guest_cmd(params.get("leapp_service_host"))
            # do preugprade test with rhsm
            upgrade_test.run_guest_cmd(params.get("pre_upgrade_rhsm"))
            # do ugprade test with rhsm
            upgrade_test.upgrade_process(params.get("process_upgrade_rhsm"))
        # after run upgrade, reboot the guest after finish preupgrade
        upgrade_test.session.sendline(params.get("reboot_cmd"))
        # post checking
        upgrade_test.session = vm.wait_for_login(timeout=6000)
        upgrade_test.post_upgrade_check(test, post_release)
        vm.verify_kernel_crash()
    finally:
        if upgrade_test.session:
            upgrade_test.session.close()
        vm.destroy()

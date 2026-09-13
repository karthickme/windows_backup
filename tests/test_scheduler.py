from folderbackup.schedule.aps import AppScheduler


def test_app_scheduler_constructs_with_system_timezone():
    sched = AppScheduler(lambda: None)
    try:
        assert sched.next_run_time() is None
    finally:
        sched.shutdown()

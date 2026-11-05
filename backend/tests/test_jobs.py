"""Check that task cancellation and shutdown have predictable behavior."""

import asyncio

from sample_backend.services.demo_jobs import DemoJobs


def test_cancel_running_job():
    async def check():
        events = []

        async def publish(name, data):
            events.append((name, data))

        jobs = DemoJobs(publish)
        job = jobs.start()
        await asyncio.sleep(0)
        cancelled = await jobs.cancel(job.id)

        assert cancelled is job
        assert job.status == "cancelled"
        assert any(name == "task.cancelled" for name, _ in events)
        assert await jobs.cancel("missing-job") is None
        await jobs.close()

    asyncio.run(check())


def test_shutdown_cancels_all_owned_tasks():
    async def check():
        async def publish(_name, _data):
            pass

        jobs = DemoJobs(publish)
        first = jobs.start()
        second = jobs.start()
        await asyncio.sleep(0)
        await jobs.close()

        assert first.status == "cancelled"
        assert second.status == "cancelled"

    asyncio.run(check())

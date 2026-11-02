import asyncio

import jobs


def test_identical_running_job_is_reused_and_refresh_is_not():
    async def scenario():
        gate = asyncio.Event()

        async def work(job):
            await gate.wait()
            return {"ok": True}

        a = jobs.start_job("unit_reuse", {"x": 1}, work)
        b = jobs.start_job("unit_reuse", {"x": 1}, work)
        c = jobs.start_job("unit_reuse", {"x": 2}, work)
        d = jobs.start_job("unit_reuse", {"x": 1, "refresh": True}, work)
        gate.set()
        await asyncio.sleep(0.05)
        e = jobs.start_job("unit_reuse", {"x": 1}, work)  # finished moments ago: reused
        return a, b, c, d, e

    a, b, c, d, e = asyncio.run(scenario())
    assert a is b and a is not c and a is not d
    assert e is a and a.status == "completed"

"""评估前文走真实持久化读取，不付费验证输入夹具的一致性。"""

import importlib.util
from pathlib import Path

from codeinsight.agent.followup import prepare_followup
from codeinsight.storage.conversations import PersistentConversationStore


def test_fixed_context_is_available_to_both_history_and_followup(conn):
    path = Path(__file__).resolve().parents[1] / "scripts/compare_understanding_replies.py"
    spec = importlib.util.spec_from_file_location("reply_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    conn.execute("INSERT INTO project(id,name,root_path) VALUES(1,'fixture','missing')")
    conn.commit()
    for number in (4, 5):
        cid = f"q{number}"
        module.seed_history(conn, 1, cid, number, module.PRIOR)
        history = PersistentConversationStore(conn).history(f"1:{cid}")
        assert len(history) == 2
        assert history[0]["content"] == module.QUESTIONS[2 if number == 4 else 1]
        assert history[1]["content"] == (module.QUERY_PROCESS if number == 4 else module.PRIOR)
        if number == 5:
            followup = prepare_followup(conn, 1, cid, module.QUESTIONS[4], history)
            assert followup["kind"] == "rephrase"
            assert followup["request_id"] == "fixed-prior"
            assert "没有可关联" not in followup["note"]

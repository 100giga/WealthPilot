import time

from wealth_pilot.memory.consolidate import consolidate
from wealth_pilot.memory.store import MemoryStore


def test_episodic_memory_persists_and_is_scoped_by_client(memory_store: MemoryStore):
    memory_store.remember_episode("client-001", "Mentioned a goal of retiring at 55.")
    memory_store.remember_episode("client-002", "Asked about gold ETFs.")
    assert len(memory_store.episodes("client-001")) == 1
    assert len(memory_store.episodes("client-002")) == 1
    assert len(memory_store.episodes()) == 2


def test_working_memory_never_persists_to_disk(memory_store: MemoryStore):
    memory_store.working.append("current turn scratch note")
    reloaded = MemoryStore(root=memory_store.root)
    assert reloaded.working == []


def test_semantic_facts_survive_a_new_store_instance_pointed_at_the_same_root(memory_store: MemoryStore):
    memory_store.remember_fact("client-001", "risk_tolerance", "moderate")
    reloaded = MemoryStore(root=memory_store.root)
    facts = {f.key: f.value for f in reloaded.facts("client-001")}
    assert facts["risk_tolerance"] == "moderate"


def test_semantic_search_ranks_relevant_memory_first(memory_store: MemoryStore):
    memory_store.remember_episode("client-001", "User has a strong preference for gold as an inflation hedge.")
    memory_store.remember_episode("client-001", "User asked about the weather in Hyderabad.")
    results = memory_store.search("client-001", "does the client like gold investments?", top_k=1)
    assert "gold" in results[0][0].lower()


def test_consolidation_prunes_expired_facts(memory_store: MemoryStore):
    memory_store.remember_fact("client-001", "trial_expiry", "trial expires soon", expires_at=time.time() - 1)
    memory_store.remember_fact("client-001", "risk_tolerance", "moderate")
    report = consolidate(memory_store, "client-001")
    assert "trial_expiry" in report.pruned_expired
    remaining_keys = {f.key for f in memory_store.facts("client-001")}
    assert "trial_expiry" not in remaining_keys
    assert "risk_tolerance" in remaining_keys


def test_consolidation_merges_near_duplicate_facts(memory_store: MemoryStore):
    memory_store.remember_fact("client-001", "contact_pref_a", "User prefers email updates", confidence=0.7)
    memory_store.remember_fact("client-001", "contact_pref_b", "User prefers to be emailed, not texted", confidence=0.95)
    report = consolidate(memory_store, "client-001")
    assert len(report.merged_groups) == 1
    assert len(memory_store.facts("client-001")) == 1
    survivor = memory_store.facts("client-001")[0]
    assert survivor.confidence == 0.95  # kept the higher-confidence version


def test_consolidation_does_not_touch_other_clients_facts(memory_store: MemoryStore):
    memory_store.remember_fact("client-001", "risk_tolerance", "moderate")
    memory_store.remember_fact("client-002", "risk_tolerance", "aggressive")
    consolidate(memory_store, "client-001")
    assert memory_store.facts("client-002")[0].value == "aggressive"

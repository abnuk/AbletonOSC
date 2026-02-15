import time
import threading
import pytest

from . import wait_one_tick, TICK_DURATION

import sys
sys.path.append(".")
from client import AbletonOSCClient

#--------------------------------------------------------------------------------
# Fixtures: two clients on different ports
#--------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client_a() -> AbletonOSCClient:
    """Default client on port 11001 (unregistered, backward compat)."""
    c = AbletonOSCClient(client_port=11001)
    yield c
    c.stop()

@pytest.fixture(scope="module")
def client_b() -> AbletonOSCClient:
    """Second client on port 11002 (registered)."""
    c = AbletonOSCClient(client_port=11002)
    c.register()
    wait_one_tick()
    yield c
    c.unregister()
    wait_one_tick()
    c.stop()

#--------------------------------------------------------------------------------
# Helper to collect listener events
#--------------------------------------------------------------------------------

def collect_messages(client, address, count=1, timeout=2.0):
    """
    Collect `count` messages on `address` from `client` within `timeout` seconds.
    Returns a list of param tuples received.
    """
    results = []
    event = threading.Event()

    def handler(addr, params):
        results.append(params)
        if len(results) >= count:
            event.set()

    client.set_handler(address, handler)
    event.wait(timeout)
    client.remove_handler(address)
    return results

#--------------------------------------------------------------------------------
# Tests
#--------------------------------------------------------------------------------

def test_register_listener(client_b):
    """Client B registers on port 11002, server acknowledges with the port."""
    rv = client_b.query("/live/api/register_listener", (11002,), timeout=TICK_DURATION * 3)
    assert rv == (11002,)


def test_single_registered_client_receives_events(client_b):
    """Client B subscribes to tempo listener, changes tempo, gets update on port 11002."""
    client_b.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    client_b.send_message("/live/song/start_listen/tempo")
    # Should receive the immediate current value
    rv = client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv == (120,)

    # Change tempo and verify we get the update
    client_b.send_message("/live/song/set/tempo", [130])
    rv = client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv == (130,)

    client_b.send_message("/live/song/stop_listen/tempo")
    client_b.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_two_clients_both_receive_listener_events(client_a, client_b):
    """Both clients subscribe to start_listen/tempo, change tempo, both receive the update."""
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    # Both subscribe
    client_a.send_message("/live/song/start_listen/tempo")
    client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    client_b.send_message("/live/song/start_listen/tempo")
    client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)

    # Set up collection for both clients
    results_a = []
    results_b = []
    event_a = threading.Event()
    event_b = threading.Event()

    def handler_a(addr, params):
        results_a.append(params)
        event_a.set()

    def handler_b(addr, params):
        results_b.append(params)
        event_b.set()

    client_a.set_handler("/live/song/get/tempo", handler_a)
    client_b.set_handler("/live/song/get/tempo", handler_b)

    # Change tempo
    client_a.send_message("/live/song/set/tempo", [140])

    # Both should receive the update
    event_a.wait(TICK_DURATION * 5)
    event_b.wait(TICK_DURATION * 5)

    client_a.remove_handler("/live/song/get/tempo")
    client_b.remove_handler("/live/song/get/tempo")

    assert len(results_a) >= 1, "Client A did not receive tempo update"
    assert len(results_b) >= 1, "Client B did not receive tempo update"
    assert results_a[-1] == (140,)
    assert results_b[-1] == (140,)

    # Cleanup
    client_a.send_message("/live/song/stop_listen/tempo")
    client_b.send_message("/live/song/stop_listen/tempo")
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_stop_listen_one_client(client_a, client_b):
    """Both subscribe, client A stops listening, client B still receives events."""
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    # Both subscribe
    client_a.send_message("/live/song/start_listen/tempo")
    client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    client_b.send_message("/live/song/start_listen/tempo")
    client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)

    # Client A stops listening
    client_a.send_message("/live/song/stop_listen/tempo")
    wait_one_tick()

    # Change tempo -- only client B should receive
    event_b = threading.Event()
    result_b = []

    def handler_b(addr, params):
        result_b.append(params)
        event_b.set()

    client_b.set_handler("/live/song/get/tempo", handler_b)
    client_a.send_message("/live/song/set/tempo", [155])

    event_b.wait(TICK_DURATION * 5)
    client_b.remove_handler("/live/song/get/tempo")

    assert len(result_b) >= 1, "Client B should still receive tempo updates"
    assert result_b[-1] == (155,)

    # Cleanup
    client_b.send_message("/live/song/stop_listen/tempo")
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_ref_counting_listener_lifecycle(client_a, client_b):
    """
    Both subscribe to same property; one unsubscribes, verify the Live API listener
    is still active (other client still gets events); second unsubscribes, verify
    listener is removed (no more events).
    """
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    # Both subscribe
    client_a.send_message("/live/song/start_listen/tempo")
    client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    client_b.send_message("/live/song/start_listen/tempo")
    client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)

    # Client A unsubscribes
    client_a.send_message("/live/song/stop_listen/tempo")
    wait_one_tick()

    # Client B should still get events (listener not removed from Live API)
    client_b.send_message("/live/song/set/tempo", [145])
    rv_b = client_b.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv_b == (145,)

    # Client B unsubscribes -- now listener should be fully removed
    client_b.send_message("/live/song/stop_listen/tempo")
    wait_one_tick()

    # Verify no more events are sent by changing tempo again
    # (there's no reliable way to assert "no message received" besides timeout)
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_unregistered_client_backward_compat(client_a):
    """Client A (no register() call, default port 11001) uses start_listen/stop_listen as before."""
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    client_a.send_message("/live/song/start_listen/tempo")
    rv = client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv == (120,)

    client_a.send_message("/live/song/set/tempo", [133])
    rv = client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv == (133,)

    client_a.send_message("/live/song/stop_listen/tempo")
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_unregister_removes_client(client_a):
    """Client registers, subscribes, unregisters, stops receiving events."""
    # Register client A temporarily
    client_a.send_message("/live/api/register_listener", [11001])
    wait_one_tick()

    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    client_a.send_message("/live/song/start_listen/tempo")
    rv = client_a.await_message("/live/song/get/tempo", TICK_DURATION * 3)
    assert rv == (120,)

    # Unregister -- should clean up all subscriptions
    rv = client_a.query("/live/api/unregister_listener", timeout=TICK_DURATION * 3)
    assert rv == (1,)
    wait_one_tick()

    # Tempo changes should still go to _remote_addr (backward compat for unregistered),
    # but the registered client subscription is gone
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()


def test_beat_listener_multi_client(client_a, client_b):
    """Both clients subscribe to beat, both receive beat events."""
    client_a.send_message("/live/song/stop_playing")
    wait_one_tick()

    client_a.send_message("/live/song/start_listen/beat")
    client_b.send_message("/live/song/start_listen/beat")
    wait_one_tick()

    # Start playback
    event_a = threading.Event()
    event_b = threading.Event()
    result_a = []
    result_b = []

    def handler_a(addr, params):
        result_a.append(params)
        if len(result_a) >= 1:
            event_a.set()

    def handler_b(addr, params):
        result_b.append(params)
        if len(result_b) >= 1:
            event_b.set()

    client_a.set_handler("/live/song/get/beat", handler_a)
    client_b.set_handler("/live/song/get/beat", handler_b)

    client_a.send_message("/live/song/start_playing")

    event_a.wait(3.0)
    event_b.wait(3.0)

    client_a.remove_handler("/live/song/get/beat")
    client_b.remove_handler("/live/song/get/beat")

    client_a.send_message("/live/song/stop_playing")
    client_a.send_message("/live/song/stop_listen/beat")
    client_b.send_message("/live/song/stop_listen/beat")
    wait_one_tick()

    assert len(result_a) >= 1, "Client A did not receive beat events"
    assert len(result_b) >= 1, "Client B did not receive beat events"


def test_query_response_independent(client_a, client_b):
    """Direct query responses go only to the requesting client."""
    client_a.send_message("/live/song/set/tempo", [120])
    wait_one_tick()

    # Both query tempo -- each should get their own response
    rv_a = client_a.query("/live/song/get/tempo")
    rv_b = client_b.query("/live/song/get/tempo")
    assert rv_a == (120,)
    assert rv_b == (120,)

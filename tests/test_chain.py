from . import client, wait_one_tick, TICK_DURATION
import pytest

#--------------------------------------------------------------------------------
# These tests assume that track 1 has an Instrument Rack (device 0) with at
# least 2 chains. This matches the default test session used for development.
#--------------------------------------------------------------------------------

TRACK_ID = 1
DEVICE_ID = 0

#--------------------------------------------------------------------------------
# Test device-scoped bulk chain queries
#--------------------------------------------------------------------------------

def test_device_get_num_chains(client):
    rv = client.query("/live/device/get/num_chains", (TRACK_ID, DEVICE_ID))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] >= 2

def test_device_get_chains_name(client):
    rv = client.query("/live/device/get/chains/name", (TRACK_ID, DEVICE_ID))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    num_chains = len(rv) - 2
    assert num_chains >= 2
    for name in rv[2:]:
        assert isinstance(name, str)

def test_device_get_chains_color_index(client):
    rv = client.query("/live/device/get/chains/color_index", (TRACK_ID, DEVICE_ID))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    for color_index in rv[2:]:
        assert isinstance(color_index, int)

def test_device_get_chains_mute(client):
    rv = client.query("/live/device/get/chains/mute", (TRACK_ID, DEVICE_ID))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    for mute in rv[2:]:
        assert isinstance(mute, (bool, int))

def test_device_get_chains_solo(client):
    rv = client.query("/live/device/get/chains/solo", (TRACK_ID, DEVICE_ID))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    for solo in rv[2:]:
        assert isinstance(solo, (bool, int))

#--------------------------------------------------------------------------------
# Test device-scoped selected chain
#--------------------------------------------------------------------------------

def test_device_get_set_selected_chain(client):
    # Get current selection to restore later
    rv_orig = client.query("/live/device/get/selected_chain", (TRACK_ID, DEVICE_ID))
    assert rv_orig[0] == TRACK_ID
    assert rv_orig[1] == DEVICE_ID
    original_chain = rv_orig[2]

    # Select chain 0
    client.send_message("/live/device/set/selected_chain", (TRACK_ID, DEVICE_ID, 0))
    wait_one_tick()
    rv = client.query("/live/device/get/selected_chain", (TRACK_ID, DEVICE_ID))
    assert rv == (TRACK_ID, DEVICE_ID, 0)

    # Select chain 1
    client.send_message("/live/device/set/selected_chain", (TRACK_ID, DEVICE_ID, 1))
    wait_one_tick()
    rv = client.query("/live/device/get/selected_chain", (TRACK_ID, DEVICE_ID))
    assert rv == (TRACK_ID, DEVICE_ID, 1)

    # Restore original
    client.send_message("/live/device/set/selected_chain", (TRACK_ID, DEVICE_ID, original_chain))
    wait_one_tick()

#--------------------------------------------------------------------------------
# Test individual chain properties (read-only)
#--------------------------------------------------------------------------------

def test_chain_get_name(client):
    rv = client.query("/live/chain/get/name", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0
    assert isinstance(rv[3], str)

def test_chain_get_color(client):
    rv = client.query("/live/chain/get/color", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0

def test_chain_get_color_index(client):
    rv = client.query("/live/chain/get/color_index", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0
    assert isinstance(rv[3], int)

#--------------------------------------------------------------------------------
# Test individual chain properties (read-write): mute, solo
#--------------------------------------------------------------------------------

def test_chain_set_get_mute(client):
    # Save original state
    rv_orig = client.query("/live/chain/get/mute", (TRACK_ID, DEVICE_ID, 0))
    original_mute = rv_orig[3]

    # Mute
    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, 1))
    wait_one_tick()
    rv = client.query("/live/chain/get/mute", (TRACK_ID, DEVICE_ID, 0))
    assert rv == (TRACK_ID, DEVICE_ID, 0, True)

    # Unmute
    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, 0))
    wait_one_tick()
    rv = client.query("/live/chain/get/mute", (TRACK_ID, DEVICE_ID, 0))
    assert rv == (TRACK_ID, DEVICE_ID, 0, False)

    # Restore
    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, original_mute))
    wait_one_tick()

def test_chain_set_get_solo(client):
    # Save original state
    rv_orig = client.query("/live/chain/get/solo", (TRACK_ID, DEVICE_ID, 0))
    original_solo = rv_orig[3]

    # Solo on
    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, 1))
    wait_one_tick()
    rv = client.query("/live/chain/get/solo", (TRACK_ID, DEVICE_ID, 0))
    assert rv == (TRACK_ID, DEVICE_ID, 0, True)

    # Solo off
    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, 0))
    wait_one_tick()
    rv = client.query("/live/chain/get/solo", (TRACK_ID, DEVICE_ID, 0))
    assert rv == (TRACK_ID, DEVICE_ID, 0, False)

    # Restore
    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, original_solo))
    wait_one_tick()

def test_chain_set_get_name(client):
    # Save original name
    rv_orig = client.query("/live/chain/get/name", (TRACK_ID, DEVICE_ID, 0))
    original_name = rv_orig[3]

    # Rename
    client.send_message("/live/chain/set/name", (TRACK_ID, DEVICE_ID, 0, "TestChain"))
    wait_one_tick()
    rv = client.query("/live/chain/get/name", (TRACK_ID, DEVICE_ID, 0))
    assert rv == (TRACK_ID, DEVICE_ID, 0, "TestChain")

    # Restore
    client.send_message("/live/chain/set/name", (TRACK_ID, DEVICE_ID, 0, original_name))
    wait_one_tick()

#--------------------------------------------------------------------------------
# Test chain mixer properties: volume, panning
#--------------------------------------------------------------------------------

def test_chain_set_get_volume(client):
    # Save original
    rv_orig = client.query("/live/chain/get/volume", (TRACK_ID, DEVICE_ID, 0))
    original_volume = rv_orig[3]

    for value in [0.5, 1.0]:
        client.send_message("/live/chain/set/volume", (TRACK_ID, DEVICE_ID, 0, value))
        wait_one_tick()
        rv = client.query("/live/chain/get/volume", (TRACK_ID, DEVICE_ID, 0))
        assert rv[0] == TRACK_ID
        assert rv[1] == DEVICE_ID
        assert rv[2] == 0
        assert abs(rv[3] - value) < 0.01

    # Restore
    client.send_message("/live/chain/set/volume", (TRACK_ID, DEVICE_ID, 0, original_volume))
    wait_one_tick()

def test_chain_set_get_panning(client):
    # Save original
    rv_orig = client.query("/live/chain/get/panning", (TRACK_ID, DEVICE_ID, 0))
    original_panning = rv_orig[3]

    for value in [-0.5, 0.5, 0.0]:
        client.send_message("/live/chain/set/panning", (TRACK_ID, DEVICE_ID, 0, value))
        wait_one_tick()
        rv = client.query("/live/chain/get/panning", (TRACK_ID, DEVICE_ID, 0))
        assert rv[0] == TRACK_ID
        assert rv[1] == DEVICE_ID
        assert rv[2] == 0
        assert abs(rv[3] - value) < 0.01

    # Restore
    client.send_message("/live/chain/set/panning", (TRACK_ID, DEVICE_ID, 0, original_panning))
    wait_one_tick()

#--------------------------------------------------------------------------------
# Test chain devices
#--------------------------------------------------------------------------------

def test_chain_get_num_devices(client):
    rv = client.query("/live/chain/get/num_devices", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0
    assert rv[3] >= 0

def test_chain_get_devices_name(client):
    rv = client.query("/live/chain/get/devices/name", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0
    for name in rv[3:]:
        assert isinstance(name, str)

def test_chain_get_devices_type(client):
    rv = client.query("/live/chain/get/devices/type", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0

def test_chain_get_devices_class_name(client):
    rv = client.query("/live/chain/get/devices/class_name", (TRACK_ID, DEVICE_ID, 0))
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0
    for class_name in rv[3:]:
        assert isinstance(class_name, str)

#--------------------------------------------------------------------------------
# Test chain listeners
#--------------------------------------------------------------------------------

def test_chain_listen_mute(client):
    # Save original
    rv_orig = client.query("/live/chain/get/mute", (TRACK_ID, DEVICE_ID, 0))
    original_mute = rv_orig[3]

    client.send_message("/live/chain/start_listen/mute", (TRACK_ID, DEVICE_ID, 0))
    rv = client.await_message("/live/chain/get/mute", TICK_DURATION * 2)
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0

    # Toggle mute and check listener fires
    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, 1))
    rv = client.await_message("/live/chain/get/mute", TICK_DURATION * 2)
    assert rv == (TRACK_ID, DEVICE_ID, 0, True)

    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, 0))
    rv = client.await_message("/live/chain/get/mute", TICK_DURATION * 2)
    assert rv == (TRACK_ID, DEVICE_ID, 0, False)

    client.send_message("/live/chain/stop_listen/mute", (TRACK_ID, DEVICE_ID, 0))

    # Restore
    client.send_message("/live/chain/set/mute", (TRACK_ID, DEVICE_ID, 0, original_mute))
    wait_one_tick()

def test_chain_listen_solo(client):
    # Save original
    rv_orig = client.query("/live/chain/get/solo", (TRACK_ID, DEVICE_ID, 0))
    original_solo = rv_orig[3]

    client.send_message("/live/chain/start_listen/solo", (TRACK_ID, DEVICE_ID, 0))
    rv = client.await_message("/live/chain/get/solo", TICK_DURATION * 2)
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    assert rv[2] == 0

    # Toggle solo and check listener fires
    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, 1))
    rv = client.await_message("/live/chain/get/solo", TICK_DURATION * 2)
    assert rv == (TRACK_ID, DEVICE_ID, 0, True)

    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, 0))
    rv = client.await_message("/live/chain/get/solo", TICK_DURATION * 2)
    assert rv == (TRACK_ID, DEVICE_ID, 0, False)

    client.send_message("/live/chain/stop_listen/solo", (TRACK_ID, DEVICE_ID, 0))

    # Restore
    client.send_message("/live/chain/set/solo", (TRACK_ID, DEVICE_ID, 0, original_solo))
    wait_one_tick()

def test_device_listen_selected_chain(client):
    client.send_message("/live/device/start_listen/selected_chain", (TRACK_ID, DEVICE_ID))
    rv = client.await_message("/live/device/get/selected_chain", TICK_DURATION * 2)
    assert rv[0] == TRACK_ID
    assert rv[1] == DEVICE_ID
    original_chain = rv[2]

    # Change selection and check listener fires
    target = 1 if original_chain != 1 else 0
    client.send_message("/live/device/set/selected_chain", (TRACK_ID, DEVICE_ID, target))
    rv = client.await_message("/live/device/get/selected_chain", TICK_DURATION * 2)
    assert rv == (TRACK_ID, DEVICE_ID, target)

    client.send_message("/live/device/stop_listen/selected_chain", (TRACK_ID, DEVICE_ID))

    # Restore
    client.send_message("/live/device/set/selected_chain", (TRACK_ID, DEVICE_ID, original_chain))
    wait_one_tick()

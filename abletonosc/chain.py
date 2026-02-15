from typing import Tuple, Any, Optional
from .handler import AbletonOSCHandler


class ChainHandler(AbletonOSCHandler):
    def __init__(self, manager):
        super().__init__(manager)
        self.class_identifier = "chain"

    def init_api(self):
        #--------------------------------------------------------------------------------
        # Callback wrappers
        #--------------------------------------------------------------------------------
        def create_device_callback(func, *args):
            """
            Wrapper for device-scoped chain operations (bulk queries, selected_chain).
            Extracts (track_index, device_index) and resolves the rack device.
            """
            def device_callback(params: Tuple[Any]):
                track_index, device_index = int(params[0]), int(params[1])
                device = self.song.tracks[track_index].devices[device_index]
                rv = func(device, *args, params[2:])
                if rv is not None:
                    return (track_index, device_index, *rv)

            return device_callback

        def create_chain_callback(func, *args, include_ids: bool = False):
            """
            Wrapper for chain-scoped operations.
            Extracts (track_index, device_index, chain_index) and resolves the chain.
            """
            def chain_callback(params: Tuple[Any]):
                track_index, device_index, chain_index = int(params[0]), int(params[1]), int(params[2])
                device = self.song.tracks[track_index].devices[device_index]
                chain = device.chains[chain_index]
                if include_ids:
                    rv = func(chain, *args, params[0:])
                else:
                    rv = func(chain, *args, params[3:])

                if rv is not None:
                    return (track_index, device_index, chain_index, *rv)

            return chain_callback

        #--------------------------------------------------------------------------------
        # Device-scoped: Bulk chain queries
        #--------------------------------------------------------------------------------
        def device_get_num_chains(device, params: Tuple[Any] = ()):
            return (len(device.chains),)

        def device_get_chains_name(device, params: Tuple[Any] = ()):
            return tuple(chain.name for chain in device.chains)

        def device_get_chains_color(device, params: Tuple[Any] = ()):
            return tuple(chain.color for chain in device.chains)

        def device_get_chains_color_index(device, params: Tuple[Any] = ()):
            return tuple(chain.color_index for chain in device.chains)

        def device_get_chains_mute(device, params: Tuple[Any] = ()):
            return tuple(chain.mute for chain in device.chains)

        def device_get_chains_solo(device, params: Tuple[Any] = ()):
            return tuple(chain.solo for chain in device.chains)

        self.osc_server.add_handler("/live/device/get/num_chains", create_device_callback(device_get_num_chains))
        self.osc_server.add_handler("/live/device/get/chains/name", create_device_callback(device_get_chains_name))
        self.osc_server.add_handler("/live/device/get/chains/color", create_device_callback(device_get_chains_color))
        self.osc_server.add_handler("/live/device/get/chains/color_index", create_device_callback(device_get_chains_color_index))
        self.osc_server.add_handler("/live/device/get/chains/mute", create_device_callback(device_get_chains_mute))
        self.osc_server.add_handler("/live/device/get/chains/solo", create_device_callback(device_get_chains_solo))

        #--------------------------------------------------------------------------------
        # Device-scoped: Selected chain (via device.view)
        #--------------------------------------------------------------------------------
        def device_get_selected_chain(device, params: Tuple[Any] = ()):
            selected = device.view.selected_chain
            if selected is not None:
                return (list(device.chains).index(selected),)
            return (None,)

        def device_set_selected_chain(device, params: Tuple[Any] = ()):
            chain_index = int(params[0])
            device.view.selected_chain = device.chains[chain_index]

        self.osc_server.add_handler("/live/device/get/selected_chain", create_device_callback(device_get_selected_chain))
        self.osc_server.add_handler("/live/device/set/selected_chain", create_device_callback(device_set_selected_chain))

        #--------------------------------------------------------------------------------
        # Device-scoped: Chain list listener (fires when chains are added/removed)
        #--------------------------------------------------------------------------------
        def device_start_listen_chains(params: Tuple[Any] = ()):
            track_index, device_index = int(params[0]), int(params[1])
            device = self.song.tracks[track_index].devices[device_index]
            self._start_listen(
                target=device, prop='chains',
                params=(track_index, device_index),
                getter=lambda: tuple(chain.name for chain in device.chains),
                osc_address="/live/device/get/chains",
                listener_name="chains")

        def device_stop_listen_chains(params: Tuple[Any] = ()):
            track_index, device_index = int(params[0]), int(params[1])
            self._stop_listen('chains', (track_index, device_index))

        self.osc_server.add_handler("/live/device/start_listen/chains", device_start_listen_chains)
        self.osc_server.add_handler("/live/device/stop_listen/chains", device_stop_listen_chains)

        #--------------------------------------------------------------------------------
        # Device-scoped: Selected chain listener
        #--------------------------------------------------------------------------------
        def device_start_listen_selected_chain(params: Tuple[Any] = ()):
            track_index, device_index = int(params[0]), int(params[1])
            device = self.song.tracks[track_index].devices[device_index]

            def selected_chain_getter():
                selected = device.view.selected_chain
                if selected is not None:
                    return (list(device.chains).index(selected),)
                return (-1,)

            self._start_listen(
                target=device.view, prop='selected_chain',
                params=(track_index, device_index),
                getter=selected_chain_getter,
                osc_address="/live/device/get/selected_chain",
                listener_name="selected_chain")

        def device_stop_listen_selected_chain(params: Tuple[Any] = ()):
            track_index, device_index = int(params[0]), int(params[1])
            self._stop_listen('selected_chain', (track_index, device_index))

        self.osc_server.add_handler("/live/device/start_listen/selected_chain", device_start_listen_selected_chain)
        self.osc_server.add_handler("/live/device/stop_listen/selected_chain", device_stop_listen_selected_chain)

        #--------------------------------------------------------------------------------
        # Chain-scoped: Individual chain properties (read-only)
        #--------------------------------------------------------------------------------
        properties_r = [
            "color",
            "color_index",
        ]
        properties_rw = [
            "name",
            "mute",
            "solo",
        ]

        for prop in properties_r + properties_rw:
            self.osc_server.add_handler("/live/chain/get/%s" % prop,
                                        create_chain_callback(self._get_property, prop))
        for prop in properties_rw:
            self.osc_server.add_handler("/live/chain/set/%s" % prop,
                                        create_chain_callback(self._set_property, prop))

        #--------------------------------------------------------------------------------
        # Chain-scoped: Listeners for mute/solo
        #--------------------------------------------------------------------------------
        for prop in properties_rw:
            self.osc_server.add_handler("/live/chain/start_listen/%s" % prop,
                                        create_chain_callback(self._start_listen, prop, include_ids=True))
            self.osc_server.add_handler("/live/chain/stop_listen/%s" % prop,
                                        create_chain_callback(self._stop_listen_compat, prop, include_ids=True))

        #--------------------------------------------------------------------------------
        # Chain-scoped: Mixer properties (volume, panning)
        # These are accessed via chain.mixer_device.volume / chain.mixer_device.panning
        #--------------------------------------------------------------------------------
        def chain_get_volume(chain, params: Tuple[Any] = ()):
            return (chain.mixer_device.volume.value,)

        def chain_set_volume(chain, params: Tuple[Any] = ()):
            chain.mixer_device.volume.value = params[0]

        def chain_get_panning(chain, params: Tuple[Any] = ()):
            return (chain.mixer_device.panning.value,)

        def chain_set_panning(chain, params: Tuple[Any] = ()):
            chain.mixer_device.panning.value = params[0]

        self.osc_server.add_handler("/live/chain/get/volume", create_chain_callback(chain_get_volume))
        self.osc_server.add_handler("/live/chain/set/volume", create_chain_callback(chain_set_volume))
        self.osc_server.add_handler("/live/chain/get/panning", create_chain_callback(chain_get_panning))
        self.osc_server.add_handler("/live/chain/set/panning", create_chain_callback(chain_set_panning))

        #--------------------------------------------------------------------------------
        # Chain-scoped: Mixer property listeners (volume, panning)
        #--------------------------------------------------------------------------------
        def chain_start_listen_mixer(chain, prop_name, params: Tuple[Any] = ()):
            parameter_object = getattr(chain.mixer_device, prop_name)
            self._start_listen(
                target=parameter_object,
                prop='chain_mixer_%s' % prop_name,
                params=params,
                getter=lambda: (parameter_object.value,),
                osc_address="/live/chain/get/%s" % prop_name,
                listener_name="value")

        def chain_stop_listen_mixer(chain, prop_name, params: Tuple[Any] = ()):
            self._stop_listen('chain_mixer_%s' % prop_name, params)

        for mixer_prop in ["volume", "panning"]:
            self.osc_server.add_handler("/live/chain/start_listen/%s" % mixer_prop,
                                        create_chain_callback(chain_start_listen_mixer, mixer_prop, include_ids=True))
            self.osc_server.add_handler("/live/chain/stop_listen/%s" % mixer_prop,
                                        create_chain_callback(chain_stop_listen_mixer, mixer_prop, include_ids=True))

        #--------------------------------------------------------------------------------
        # Chain-scoped: Devices within chain
        #--------------------------------------------------------------------------------
        def chain_get_num_devices(chain, params: Tuple[Any] = ()):
            return (len(chain.devices),)

        def chain_get_devices_name(chain, params: Tuple[Any] = ()):
            return tuple(device.name for device in chain.devices)

        def chain_get_devices_type(chain, params: Tuple[Any] = ()):
            return tuple(device.type for device in chain.devices)

        def chain_get_devices_class_name(chain, params: Tuple[Any] = ()):
            return tuple(device.class_name for device in chain.devices)

        self.osc_server.add_handler("/live/chain/get/num_devices", create_chain_callback(chain_get_num_devices))
        self.osc_server.add_handler("/live/chain/get/devices/name", create_chain_callback(chain_get_devices_name))
        self.osc_server.add_handler("/live/chain/get/devices/type", create_chain_callback(chain_get_devices_type))
        self.osc_server.add_handler("/live/chain/get/devices/class_name", create_chain_callback(chain_get_devices_class_name))

        #--------------------------------------------------------------------------------
        # Chain-scoped: Bulk enable/disable all devices in a chain
        # Sets parameter 0 ("Device On") for every device in the chain.
        #--------------------------------------------------------------------------------
        def chain_set_devices_enabled(chain, params: Tuple[Any] = ()):
            enabled = float(params[0])
            for device in chain.devices:
                device.parameters[0].value = enabled

        self.osc_server.add_handler("/live/chain/set/devices_enabled", create_chain_callback(chain_set_devices_enabled))

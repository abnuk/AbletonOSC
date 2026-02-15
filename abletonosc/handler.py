from ableton.v2.control_surface.component import Component
from typing import Optional, Tuple, Set, Dict, Any
import logging
from .osc_server import OSCServer

class AbletonOSCHandler(Component):
    def __init__(self, manager):
        super().__init__()

        self.logger = logging.getLogger("abletonosc")
        self.manager = manager
        self.osc_server: OSCServer = self.manager.osc_server
        self.init_api()

        # listener_key -> callback function registered with Live API
        self.listener_functions: Dict = {}
        # listener_key -> (target, listener_name) for cleanup
        self.listener_objects: Dict = {}
        # listener_key -> set of registered (ip, port) client addresses
        self.listener_clients: Dict[Any, Set[Tuple[str, int]]] = {}
        # listener_key -> total subscriber count (registered + unregistered)
        self.listener_ref_count: Dict[Any, int] = {}

        self.class_identifier = None

    def init_api(self):
        pass

    def clear_api(self):
        self._clear_listeners()

    #--------------------------------------------------------------------------------
    # Generic callbacks
    #--------------------------------------------------------------------------------
    def _call_method(self, target, method, params: Optional[Tuple] = ()):
        self.logger.info("Calling method for %s: %s (params %s)" % (self.class_identifier, method, str(params)))
        getattr(target, method)(*params)

    def _set_property(self, target, prop, params: Tuple) -> None:
        self.logger.info("Setting property for %s: %s (new value %s)" % (self.class_identifier, prop, params[0]))
        setattr(target, prop, params[0])

    def _get_property(self, target, prop, params: Optional[Tuple] = ()) -> Tuple[Any]:
        try:
            value = getattr(target, prop)
        except RuntimeError:
            #--------------------------------------------------------------------------------
            # Gracefully handle errors, which may occur when querying parameters that don't apply
            # to a particular object (e.g. track.fold_state for a non-group track)
            #--------------------------------------------------------------------------------
            value = None
        self.logger.info("Getting property for %s: %s = %s" % (self.class_identifier, prop, value))
        return (value, *params)

    def _start_listen(self, target, prop, params: Optional[Tuple] = (),
                      getter=None, on_change=None,
                      osc_address=None, listener_name=None) -> None:
        """
        Unified listener registration with multi-client support.

        Registers a Live API listener for property `prop` on object `target`.
        Supports ref counting so multiple clients can subscribe to the same listener.
        When the property changes, the callback broadcasts to all subscribed registered
        clients plus the default _remote_addr (for backward compatibility).

        Args:
            target: The Live API object to attach the listener to.
            prop: Property name. Used for: listener key, default listener method name,
                  default getter, default OSC address.
            params: Identifying tuple (e.g. track_index, clip_index).
            getter: Optional custom value getter: () -> value.
                    For legacy callers that pass getter(params), a function accepting
                    params is also supported.
                    Default: lambda: getattr(target, prop)
            on_change: Optional fully custom change handler: (broadcast_fn) -> None.
                       If provided, overrides getter. The broadcast_fn(address, params)
                       sends to all subscribed clients.
                       Used for special cases like beat listener (conditional) or
                       device parameter (2 messages per event).
            osc_address: Custom OSC address. Default: /live/{class_identifier}/get/{prop}
            listener_name: Base name for add_X_listener/remove_X_listener methods.
                          Default: prop. Use "value" for mixer/parameter listeners.
        """
        listener_key = (prop, tuple(params))
        ln = listener_name or prop
        addr = osc_address or "/live/%s/get/%s" % (self.class_identifier, prop)
        client_addr = self.osc_server._current_client_addr

        #--------------------------------------------------------------------------------
        # If this listener already exists, just add the new client subscriber
        # and increment the ref count.
        #--------------------------------------------------------------------------------
        if listener_key in self.listener_ref_count and self.listener_ref_count[listener_key] > 0:
            self.listener_ref_count[listener_key] += 1
            if client_addr is not None:
                self.listener_clients.setdefault(listener_key, set()).add(client_addr)
            self.logger.info("Added subscriber for %s %s, property: %s (ref_count=%d)" %
                             (self.class_identifier, str(params), prop, self.listener_ref_count[listener_key]))
            #--------------------------------------------------------------------------------
            # Send immediate current value to the requesting client only.
            #--------------------------------------------------------------------------------
            self._send_immediate_value(target, prop, params, getter, on_change, addr, client_addr)
            return

        #--------------------------------------------------------------------------------
        # First subscriber -- register the Live API listener.
        #--------------------------------------------------------------------------------
        def property_changed_callback():
            clients = self.listener_clients.get(listener_key, set())
            if on_change is not None:
                def broadcast_fn(bcast_address, bcast_params):
                    self.osc_server.broadcast(bcast_address, bcast_params, clients)
                on_change(broadcast_fn)
            else:
                if getter is not None:
                    # Support both () -> value and (params) -> value signatures
                    try:
                        value = getter()
                    except TypeError:
                        value = getter(params)
                else:
                    value = getattr(target, prop)
                if type(value) is not tuple:
                    value = (value,)
                self.logger.info("Property %s changed of %s %s: %s" %
                                 (prop, self.class_identifier, str(params), value))
                self.osc_server.broadcast(addr, (*params, *value,), clients)

        self.listener_ref_count[listener_key] = 1
        if client_addr is not None:
            self.listener_clients.setdefault(listener_key, set()).add(client_addr)

        self.logger.info("Adding listener for %s %s, property: %s" %
                         (self.class_identifier, str(params), prop))
        add_listener_function_name = "add_%s_listener" % ln
        add_listener_function = getattr(target, add_listener_function_name)
        add_listener_function(property_changed_callback)
        self.listener_functions[listener_key] = property_changed_callback
        self.listener_objects[listener_key] = (target, ln)

        #--------------------------------------------------------------------------------
        # Immediately send the current value to the requesting client.
        #--------------------------------------------------------------------------------
        self._send_immediate_value(target, prop, params, getter, on_change, addr, client_addr)

    def _send_immediate_value(self, target, prop, params, getter, on_change, addr, client_addr):
        """
        Send the current value of a property to a specific client (or _remote_addr).
        Called when a client first subscribes to a listener.
        """
        if on_change is not None:
            # For on_change listeners, call with a send function targeting only this client
            def send_to_requester(bcast_address, bcast_params):
                if client_addr is not None:
                    self.osc_server.send(bcast_address, bcast_params, remote_addr=client_addr)
                else:
                    self.osc_server.send(bcast_address, bcast_params)
            on_change(send_to_requester)
        else:
            if getter is not None:
                try:
                    value = getter()
                except TypeError:
                    value = getter(params)
            else:
                value = getattr(target, prop)
            if type(value) is not tuple:
                value = (value,)
            if client_addr is not None:
                self.osc_server.send(addr, (*params, *value,), remote_addr=client_addr)
            else:
                self.osc_server.send(addr, (*params, *value,))

    def _stop_listen(self, prop, params: Optional[Tuple[Any]] = ()) -> None:
        """
        Stop listening for a property. Supports multi-client ref counting.

        Decrements the ref count. If the requesting client is registered, removes
        them from listener_clients. Only removes the Live API listener when
        ref_count reaches 0.

        Note: the target object is looked up from listener_objects, so callers
        no longer need to pass it.
        """
        listener_key = (prop, tuple(params))
        client_addr = self.osc_server._current_client_addr

        # Remove this client from the subscriber set
        if client_addr is not None and listener_key in self.listener_clients:
            self.listener_clients[listener_key].discard(client_addr)

        # Decrement ref count
        if listener_key not in self.listener_ref_count or self.listener_ref_count[listener_key] <= 0:
            self.logger.warning("No listener found for property: %s (%s)" % (prop, str(params)))
            return

        self.listener_ref_count[listener_key] -= 1
        if self.listener_ref_count[listener_key] > 0:
            self.logger.info("Decremented subscriber for %s %s, property: %s (ref_count=%d)" %
                             (self.class_identifier, str(params), prop, self.listener_ref_count[listener_key]))
            return

        #--------------------------------------------------------------------------------
        # Last subscriber -- remove the Live API listener.
        #--------------------------------------------------------------------------------
        if listener_key in self.listener_functions:
            self.logger.info("Removing listener for %s %s, property %s" %
                             (self.class_identifier, str(params), prop))
            listener_function = self.listener_functions[listener_key]
            target, ln = self.listener_objects[listener_key]
            remove_listener_function_name = "remove_%s_listener" % ln
            remove_listener_function = getattr(target, remove_listener_function_name)
            try:
                remove_listener_function(listener_function)
            except Exception as e:
                #--------------------------------------------------------------------------------
                # This exception may be thrown when an observer is no longer connected --
                # e.g., when trying to stop listening for a clip property of a clip that has been deleted.
                # Ignore as it is benign.
                #--------------------------------------------------------------------------------
                self.logger.info("Exception whilst removing listener (likely benign): %s" % e)

            del self.listener_functions[listener_key]
            del self.listener_objects[listener_key]
        if listener_key in self.listener_clients:
            del self.listener_clients[listener_key]
        del self.listener_ref_count[listener_key]

    def _stop_listen_compat(self, _target, prop, params: Optional[Tuple[Any]] = ()) -> None:
        """
        Backward-compatible wrapper for _stop_listen that accepts (and ignores) a target
        argument. Used by existing handler registrations that pass target via partial().
        """
        self._stop_listen(prop, params)

    def _clear_listeners(self):
        """
        Clears all listener functions, to prevent listeners continuing to report after a reload.
        Forces removal of all Live API listeners regardless of ref counts.
        """
        for listener_key in list(self.listener_functions.keys())[:]:
            listener_function = self.listener_functions[listener_key]
            target, ln = self.listener_objects[listener_key]
            remove_listener_function_name = "remove_%s_listener" % ln
            remove_listener_function = getattr(target, remove_listener_function_name)
            try:
                remove_listener_function(listener_function)
            except Exception as e:
                self.logger.info("Exception whilst removing listener (likely benign): %s" % e)
        self.listener_functions.clear()
        self.listener_objects.clear()
        self.listener_clients.clear()
        self.listener_ref_count.clear()

    def remove_client_from_all_listeners(self, client_addr: Tuple[str, int]) -> None:
        """
        Remove a client from all listener subscriptions and decrement ref counts.
        Called when a client unregisters.
        """
        for listener_key in list(self.listener_clients.keys()):
            if listener_key in self.listener_clients and client_addr in self.listener_clients[listener_key]:
                self.listener_clients[listener_key].discard(client_addr)
                if listener_key in self.listener_ref_count:
                    self.listener_ref_count[listener_key] -= 1
                    if self.listener_ref_count[listener_key] <= 0:
                        # Last subscriber -- remove the Live API listener
                        prop, params = listener_key
                        self._remove_live_listener(listener_key)

    def _remove_live_listener(self, listener_key):
        """
        Remove a Live API listener by key. Cleans up all associated state.
        """
        if listener_key not in self.listener_functions:
            return
        listener_function = self.listener_functions[listener_key]
        target, ln = self.listener_objects[listener_key]
        remove_listener_function_name = "remove_%s_listener" % ln
        remove_listener_function = getattr(target, remove_listener_function_name)
        try:
            remove_listener_function(listener_function)
        except Exception as e:
            self.logger.info("Exception whilst removing listener (likely benign): %s" % e)
        del self.listener_functions[listener_key]
        del self.listener_objects[listener_key]
        if listener_key in self.listener_clients:
            del self.listener_clients[listener_key]
        if listener_key in self.listener_ref_count:
            del self.listener_ref_count[listener_key]

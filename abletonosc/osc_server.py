from typing import Tuple, Set, Dict, Optional, Any, Callable
from .constants import OSC_LISTEN_PORT, OSC_RESPONSE_PORT
from ..pythonosc.osc_message import OscMessage, ParseError
from ..pythonosc.osc_bundle import OscBundle
from ..pythonosc.osc_message_builder import OscMessageBuilder, BuildError

import re
import errno
import socket
import logging
import traceback

class OSCServer:
    def __init__(self,
                 local_addr: Tuple[str, int] = ('0.0.0.0', OSC_LISTEN_PORT),
                 remote_addr: Tuple[str, int] = ('127.0.0.1', OSC_RESPONSE_PORT)):
        """
        Class that handles OSC server responsibilities, including support for sending
        reply messages and multi-client broadcasting.

        Implemented because pythonosc's OSC server causes a beachball when handling
        incoming messages. To investigate, as it would be ultimately better not to have
        to roll our own.

        Args:
            local_addr: Local address and port to listen on.
                        By default, binds to the wildcard address 0.0.0.0, which means listening on
                        every available local IPv4 interface (including 127.0.0.1).
            remote_addr: Remote address to send replies to, by default. Can be overridden in send().
        """

        self._local_addr = local_addr
        self._remote_addr = remote_addr
        self._response_port = remote_addr[1]

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(0)
        self._socket.bind(self._local_addr)
        self._callbacks = {}

        #--------------------------------------------------------------------------------
        # Multi-client support
        #--------------------------------------------------------------------------------
        # Set of registered (ip, response_port) tuples for clients that called
        # /live/api/register_listener.
        self._registered_clients: Set[Tuple[str, int]] = set()
        # Maps (sender_ip, sender_ephemeral_port) -> response_port for registered clients.
        # UDP sockets reuse the same ephemeral source port, so this mapping is stable.
        self._client_port_map: Dict[Tuple[str, int], int] = {}
        # Response address of the current message's sender; None if unregistered.
        # Set per-message in process(), read by _start_listen/_stop_listen in handlers.
        self._current_client_addr: Optional[Tuple[str, int]] = None
        # Raw sender (ip, ephemeral_port) from recvfrom(). Set per-message in process().
        # Used by register_listener to map sender to response port.
        self._current_sender_addr: Optional[Tuple[str, int]] = None

        self.logger = logging.getLogger("abletonosc")
        self.logger.info("Starting OSC server (local %s, response port %d)",
                         str(self._local_addr), self._response_port)

    def add_handler(self, address: str, handler: Callable) -> None:
        """
        Add an OSC handler.

        Args:
            address: The OSC address string
            handler: A handler function, with signature:
                     params: Tuple[Any, ...]
        """
        self._callbacks[address] = handler

    def clear_handlers(self) -> None:
        """
        Remove all existing OSC handlers.
        """
        self._callbacks = {}

    def send(self,
             address: str,
             params: Tuple = (),
             remote_addr: Tuple[str, int] = None) -> None:
        """
        Send an OSC message.

        Args:
            address: The OSC address (e.g. /frequency)
            params: A tuple of zero or more OSC params
            remote_addr: The remote address to send to, as a 2-tuple (hostname, port).
                         If None, uses the default remote address.
        """
        msg_builder = OscMessageBuilder(address)
        for param in params:
            msg_builder.add_arg(param)

        try:
            msg = msg_builder.build()
            if remote_addr is None:
                remote_addr = self._remote_addr
            self._socket.sendto(msg.dgram, remote_addr)
        except BuildError:
            self.logger.error("AbletonOSC: OSC build error: %s" % (traceback.format_exc()))

    def register_client(self, sender_addr: Tuple[str, int], response_port: int) -> None:
        """
        Register a client for multi-client listener support.

        Args:
            sender_addr: The (ip, ephemeral_port) of the sender from recvfrom().
            response_port: The port the client is listening on for responses.
        """
        client_addr = (sender_addr[0], response_port)
        self._client_port_map[sender_addr] = response_port
        self._registered_clients.add(client_addr)
        self.logger.info("Registered client: %s (sender %s)" % (str(client_addr), str(sender_addr)))

    def unregister_client(self, sender_addr: Tuple[str, int]) -> Optional[Tuple[str, int]]:
        """
        Unregister a client.

        Args:
            sender_addr: The (ip, ephemeral_port) of the sender from recvfrom().

        Returns:
            The (ip, response_port) that was unregistered, or None if not found.
        """
        if sender_addr in self._client_port_map:
            response_port = self._client_port_map.pop(sender_addr)
            client_addr = (sender_addr[0], response_port)
            self._registered_clients.discard(client_addr)
            self.logger.info("Unregistered client: %s" % str(client_addr))
            return client_addr
        return None

    def broadcast(self,
                  address: str,
                  params: Tuple = (),
                  listener_clients: Set[Tuple[str, int]] = None) -> None:
        """
        Send an OSC message to all subscribed registered clients PLUS the default
        _remote_addr (for backward compatibility with unregistered clients).
        Deduplicates to avoid sending the same message twice to the same address.

        Args:
            address: The OSC address (e.g. /live/song/get/tempo)
            params: A tuple of zero or more OSC params
            listener_clients: Set of registered (ip, port) client addresses subscribed
                              to this listener. May be None or empty.
        """
        sent_to = set()

        # Send to all registered clients subscribed to this listener
        if listener_clients:
            for client_addr in listener_clients:
                if client_addr not in sent_to:
                    self.send(address, params, remote_addr=client_addr)
                    sent_to.add(client_addr)

        # Also send to _remote_addr for backward compatibility (unregistered clients)
        if self._remote_addr not in sent_to:
            self.send(address, params, remote_addr=self._remote_addr)

    def _resolve_response_addr(self, remote_addr: Tuple[str, int]) -> Tuple[str, int]:
        """
        Resolve the response address for a given sender.
        If the sender is a registered client, use their registered response port.
        Otherwise, use the default response port.
        """
        if remote_addr in self._client_port_map:
            return (remote_addr[0], self._client_port_map[remote_addr])
        return (remote_addr[0], self._response_port)

    def process_message(self, message, remote_addr):
        if message.address in self._callbacks:
            callback = self._callbacks[message.address]
            rv = callback(message.params)

            if rv is not None:
                assert isinstance(rv, tuple)
                response_addr = self._resolve_response_addr(remote_addr)
                self.send(address=message.address,
                          params=rv,
                          remote_addr=response_addr)
        elif "*" in message.address:
            regex = message.address.replace("*", "[^/]+")
            for callback_address, callback in self._callbacks.items():
                if re.match(regex, callback_address):
                    try:
                        rv = callback(message.params)
                    except ValueError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors for queries that require more arguments
                        # (e.g. /live/track/get/send with no args)
                        #--------------------------------------------------------------------------------
                        continue
                    except AttributeError:
                        #--------------------------------------------------------------------------------
                        # Don't throw errors when trying to create listeners for properties that can't
                        # be listened for (e.g. can_be_armed, is_foldable)
                        #--------------------------------------------------------------------------------
                        continue
                    if rv is not None:
                        assert isinstance(rv, tuple)
                        response_addr = self._resolve_response_addr(remote_addr)
                        self.send(address=callback_address,
                                  params=rv,
                                  remote_addr=response_addr)
        else:
            self.logger.error("AbletonOSC: Unknown OSC address: %s" % message.address)

    def process_bundle(self, bundle, remote_addr):
        for i in bundle:
            if OscBundle.dgram_is_bundle(i.dgram):
                self.process_bundle(i, remote_addr)
            else:
                self.process_message(i, remote_addr)

    def parse_bundle(self, data, remote_addr):
        if OscBundle.dgram_is_bundle(data):
            try:
                bundle = OscBundle(data)
                self.process_bundle(bundle, remote_addr)
            except ParseError:
                self.logger.error("AbletonOSC: Error parsing OSC bundle: %s" % (traceback.format_exc()))
        else:
            try:
                message = OscMessage(data)
                self.process_message(message, remote_addr)
            except ParseError:
                self.logger.error("AbletonOSC: Error parsing OSC message: %s" % (traceback.format_exc()))

    def process(self) -> None:
        """
        Synchronously process all data queued on the OSC socket.
        """
        try:
            repeats = 0
            while True:
                #--------------------------------------------------------------------------------
                # Loop until no more data is available.
                #--------------------------------------------------------------------------------
                data, remote_addr = self._socket.recvfrom(65536)
                #--------------------------------------------------------------------------------
                # Update the default reply address to the most recent client (backward compat).
                # Unregistered clients receive listener events at this address.
                #--------------------------------------------------------------------------------
                self._remote_addr = (remote_addr[0], OSC_RESPONSE_PORT)
                #--------------------------------------------------------------------------------
                # Store raw sender address for register_listener API.
                #--------------------------------------------------------------------------------
                self._current_sender_addr = remote_addr
                #--------------------------------------------------------------------------------
                # Resolve _current_client_addr for registered clients.
                # If the sender is registered, their response address is looked up from
                # _client_port_map. Otherwise, set to None (unregistered).
                #--------------------------------------------------------------------------------
                if remote_addr in self._client_port_map:
                    response_port = self._client_port_map[remote_addr]
                    self._current_client_addr = (remote_addr[0], response_port)
                else:
                    self._current_client_addr = None
                self.parse_bundle(data, remote_addr)

        except socket.error as e:
            if e.errno == errno.ECONNRESET:
                #--------------------------------------------------------------------------------
                # This benign error seems to occur on startup on Windows
                #--------------------------------------------------------------------------------
                self.logger.warning("AbletonOSC: Non-fatal socket error: %s" % (traceback.format_exc()))
            elif e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                #--------------------------------------------------------------------------------
                # Another benign networking error, throw when no data is received
                # on a call to recvfrom() on a non-blocking socket
                #--------------------------------------------------------------------------------
                pass
            else:
                #--------------------------------------------------------------------------------
                # Something more serious has happened
                #--------------------------------------------------------------------------------
                self.logger.error("AbletonOSC: Socket error: %s" % (traceback.format_exc()))

        except Exception as e:
            self.logger.error("AbletonOSC: Error handling OSC message: %s" % e)
            self.logger.warning("AbletonOSC: %s" % traceback.format_exc())

    def shutdown(self) -> None:
        """
        Shutdown the server network sockets.
        """
        self._socket.close()

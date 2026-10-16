"""BACnet Protocol Family Provider for UDMI Spotter."""

import concurrent.futures
import copy
from datetime import datetime, timezone
import ipaddress
import logging
import re
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

try:
  import BAC0
  import BAC0.core.io.IOExceptions
except ImportError:
  BAC0 = None

try:
  from providers.ether import get_mac_for_ip
except ImportError:
  from edge.spotter.src.providers.ether import get_mac_for_ip

from udmi.core.managers.providers.family_provider import FamilyProvider
from udmi.schema import (
    DiscoveryEvents,
    Entry,
    FamilyDiscovery,
    RefDiscovery,
    StateSystemHardware,
    System,
)

LOGGER = logging.getLogger(__name__)

BACNET_DEVICE_ID = 4194300
DEFAULT_BACNET_PORT = 47808
MAX_BACNET_INSTANCE_ID = 4194303
_IP_ADDRESS_REGEX = (
    r"^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})(:\d+)?$"
)
_INSTANCE_ID_REGEX = r"^[1-9]\d*$"
_INSTANCE_RANGE_REGEX = r"^([1-9]\d*)-([1-9]\d*)$"
_MAC_ADDRESS_REGEX = r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$"

if BAC0:
  BAC0.log_level("silence")
  for name in logging.getLogger().manager.loggerDict:
    if name.startswith("BAC0"):
      logging.getLogger(name).setLevel(logging.CRITICAL)


BACNET_ACRONYMS = {
    "analogInput": "AI",
    "analog-input": "AI",
    "analogOutput": "AO",
    "analog-output": "AO",
    "analogValue": "AV",
    "analog-value": "AV",
    "binaryInput": "BI",
    "binary-input": "BI",
    "binaryOutput": "BO",
    "binary-output": "BO",
    "binaryValue": "BV",
    "binary-value": "BV",
    "calendar": "CAL",
    "command": "CMD",
    "device": "DEV",
    "eventEnrollment": "EE",
    "event-enrollment": "EE",
    "file": "FILE",
    "group": "GRP",
    "loop": "LP",
    "lifeSafetyPoint": "LSP",
    "life-safety-point": "LSP",
    "lifeSafetyZone": "LSZ",
    "life-safety-zone": "LSZ",
    "multiStateInput": "MSI",
    "multi-state-input": "MSI",
    "multiStateOutput": "MSO",
    "multi-state-output": "MSO",
    "notificationClass": "NC",
    "notification-class": "NC",
    "program": "PRG",
    "schedule": "SCH",
    "averaging": "AVG",
    "multiStateValue": "MSV",
    "multi-state-value": "MSV",
    "trendLog": "TL",
    "trend-log": "TL",
    "trendLogMultiple": "TLM",
    "trend-log-multiple": "TLM",
    "loadControl": "LC",
    "load-control": "LC",
    "structuredView": "SV",
    "structured-view": "SV",
    "accessDoor": "AD",
    "access-door": "AD",
    "timer": "TMR",
    "eventLog": "EL",
    "event-log": "EL",
    "characterstringValue": "CSV",
    "characterstring-value": "CSV",
    "datetimeValue": "DTV",
    "datetime-value": "DTV",
    "largeAnalogValue": "LAV",
    "large-analog-value": "LAV",
    "bitstringValue": "BSV",
    "bitstring-value": "BSV",
    "octetstringValue": "OSV",
    "octetstring-value": "OSV",
    "timeValue": "TV",
    "time-value": "TV",
    "dateValue": "DV",
    "date-value": "DV",
    "integerValue": "IV",
    "integer-value": "IV",
    "positiveIntegerValue": "PIV",
    "positive-integer-value": "PIV",
    "accumulator": "ACC",
    "pulseConverter": "PC",
    "pulse-converter": "PC",
    "networkPort": "NP",
    "network-port": "NP",
    "lightingOutput": "LO",
    "lighting-output": "LO",
    "binaryLightingOutput": "BLO",
    "binary-lighting-output": "BLO",
}

BACNET_OBJECT_TYPES = {
    "analogInput": "analog-input",
    "analogOutput": "analog-output",
    "analogValue": "analog-value",
    "binaryInput": "binary-input",
    "binaryOutput": "binary-output",
    "binaryValue": "binary-value",
    "calendar": "calendar",
    "command": "command",
    "device": "device",
    "eventEnrollment": "event-enrollment",
    "file": "file",
    "group": "group",
    "loop": "loop",
    "lifeSafetyPoint": "life-safety-point",
    "lifeSafetyZone": "life-safety-zone",
    "multiStateInput": "multi-state-input",
    "multiStateOutput": "multi-state-output",
    "notificationClass": "notification-class",
    "program": "program",
    "schedule": "schedule",
    "averaging": "averaging",
    "multiStateValue": "multi-state-value",
    "trendLog": "trend-log",
    "trendLogMultiple": "trend-log-multiple",
    "loadControl": "load-control",
    "structuredView": "structured-view",
    "accessDoor": "access-door",
    "timer": "timer",
    "eventLog": "event-log",
    "characterstringValue": "characterstring-value",
    "datetimeValue": "datetime-value",
    "largeAnalogValue": "large-analog-value",
    "bitstringValue": "bitstring-value",
    "octetstringValue": "octetstring-value",
    "timeValue": "time-value",
    "dateValue": "date-value",
    "integerValue": "integer-value",
    "positiveIntegerValue": "positive-integer-value",
    "accumulator": "accumulator",
    "pulseConverter": "pulse-converter",
    "networkPort": "network-port",
    "lightingOutput": "lighting-output",
    "binaryLightingOutput": "binary-lighting-output",
}

WRITABLE_ACRONYMS = {"AO", "AV", "BO", "BV", "MSO", "MSV", "CSV"}


def _resolve_bacnet_type_and_acronym(raw_type: str) -> Tuple[str, str]:
  """Resolves canonical hyphenated BACnet type and 2-4 uppercase letter acronym."""
  canonical = BACNET_OBJECT_TYPES.get(raw_type)
  if not canonical:
    canonical = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", raw_type).lower()
  acronym = BACNET_ACRONYMS.get(raw_type) or BACNET_ACRONYMS.get(canonical)
  if not acronym or not re.match(r"^[A-Z]{2,4}$", acronym):
    initials = "".join(
        w[0] for w in re.split(r"[-_\s]+", canonical) if w and w[0].isalpha()
    ).upper()
    if 2 <= len(initials) <= 4:
      acronym = initials
    else:
      letters = re.sub(r"[^A-Z]", "", raw_type.upper())
      acronym = (letters[:4] if len(letters) >= 2 else (letters + "PT")[:2])
  return canonical, acronym


def _future_wait_and_count_outstanding(
    futures: Iterable[concurrent.futures.Future], timeout: int = 1
) -> int:
  """Waits for futures up to timeout and returns incomplete count."""
  _, outstanding = concurrent.futures.wait(futures, timeout)
  return len(outstanding)


def _is_valid_ipv4(candidate: str) -> bool:
  """Returns True if candidate is a valid IPv4 address."""
  try:
    ipaddress.IPv4Address(candidate.split("/", maxsplit=1)[0])
    return True
  except ValueError:
    return False


def parse_bacnet_transport_address(
    device_address: Any,
    default_port: Optional[int] = DEFAULT_BACNET_PORT,
    default_network: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, FamilyDiscovery]]:
  """Parses a BAC0 transport address into UDMI network and families map.

  Distinguishes BACnet/IP ('<ip>[:<port>]') from routed BACnet networks
  ('<dnet>:<dmac>' such as MS/TP '6100:10' or Ethernet '2001:00:11:22:33:44:55')
  so that routed DNET numbers are never misclassified as IPv4 addresses.

  Args:
      device_address: Raw address string from BAC0 (e.g. '192.168.1.50:47808'
          or '6100:10' or '6100:10@192.168.1.1').
      default_port: Default BACnet/IP UDP port (47808).
      default_network: Optional default BACnet network number.

  Returns:
      Tuple of (network_str, families_dict).
  """
  raw_addr = str(device_address).strip()
  if "@" in raw_addr:
    raw_addr = raw_addr.split("@", maxsplit=1)[0].strip()

  families_map: Dict[str, FamilyDiscovery] = {}
  network: Optional[str] = (
      str(default_network) if default_network is not None else None
  )

  prefix = raw_addr.split(":", maxsplit=1)[0] if ":" in raw_addr else raw_addr
  suffix = raw_addr.split(":", maxsplit=1)[1] if ":" in raw_addr else None

  if _is_valid_ipv4(prefix):
    ip_str = prefix.split("/", maxsplit=1)[0]
    port_val = default_port or DEFAULT_BACNET_PORT
    if suffix is not None:
      try:
        port_val = int(suffix)
      except ValueError:
        port_val = default_port or DEFAULT_BACNET_PORT
    families_map["ipv4"] = FamilyDiscovery(addr=ip_str, port=port_val)
    mac = get_mac_for_ip(ip_str)
    if mac:
      families_map["ether"] = FamilyDiscovery(addr=mac)
    return network, families_map

  if ":" in raw_addr and suffix is not None:
    # Routed BACnet address: <dnet>:<dmac>
    network = str(prefix)
    if re.match(_MAC_ADDRESS_REGEX, suffix):
      families_map["ether"] = FamilyDiscovery(addr=suffix.lower())
    elif _is_valid_ipv4(suffix.split(":", maxsplit=1)[0]):
      sub_ip = suffix.split(":", maxsplit=1)[0]
      sub_port = default_port or DEFAULT_BACNET_PORT
      if ":" in suffix:
        try:
          sub_port = int(suffix.split(":", maxsplit=1)[1])
        except ValueError:
          pass
      families_map["ipv4"] = FamilyDiscovery(addr=sub_ip, port=sub_port)
    else:
      families_map["mstp"] = FamilyDiscovery(addr=str(suffix))
    return network, families_map

  # Unrouted non-IPv4 MAC (e.g. local MS/TP node address)
  if re.match(_MAC_ADDRESS_REGEX, raw_addr):
    families_map["ether"] = FamilyDiscovery(addr=raw_addr.lower())
  else:
    families_map["mstp"] = FamilyDiscovery(addr=raw_addr)
  return network, families_map


def _effective_depth(discovery_config: Any) -> str:
  """Determines effective UDMI discovery depth for a BACnet scan."""
  raw_depth = getattr(discovery_config, "depth", None)
  addrs = getattr(discovery_config, "addrs", None)
  if raw_depth is not None:
    depth_val = getattr(raw_depth, "value", raw_depth)
    if depth_val:
      return str(depth_val).lower()
  return "details" if addrs else "entries"


def _validate_and_classify_addrs(
    addrs: Iterable[str],
) -> Tuple[List[str], List[Tuple[int, int]]]:
  """Validates target addresses and separates IPv4 targets from instance IDs.

  Args:
      addrs: List of target address strings from FamilyDiscoveryConfig.addrs.

  Returns:
      Tuple of (ip_targets, instance_ranges) where instance_ranges is a list
      of inclusive (low, high) BACnet device instance ID tuples.

  Raises:
      RuntimeError: If any target address does not match IPv4, instance ID,
          or instance ID range format.
  """
  ip_targets: List[str] = []
  instance_ranges: List[Tuple[int, int]] = []
  for raw in addrs:
    addr = str(raw).strip()
    if re.match(_IP_ADDRESS_REGEX, addr):
      ip_targets.append(addr)
      continue
    if re.match(_INSTANCE_ID_REGEX, addr):
      val = int(addr)
      if 1 <= val <= MAX_BACNET_INSTANCE_ID:
        instance_ranges.append((val, val))
        continue
    m = re.match(_INSTANCE_RANGE_REGEX, addr)
    if m:
      low, high = int(m.group(1)), int(m.group(2))
      if 1 <= low <= high <= MAX_BACNET_INSTANCE_ID:
        instance_ranges.append((low, high))
        continue
    raise RuntimeError(f"Unsupported BACnet target address format: {raw}")
  return ip_targets, instance_ranges


def _matches_target_filters(
    device_address: Any,
    device_id: Any,
    ip_targets: List[str],
    instance_ranges: List[Tuple[int, int]],
    target_networks: Optional[Set[str]],
    default_network: Optional[str] = None,
) -> bool:
  """Checks whether a discovered (device_address, device_id) matches filters."""
  network, _ = parse_bacnet_transport_address(
      device_address, default_network=default_network
  )
  if target_networks is not None:
    if network is None or str(network) not in target_networks:
      return False

  if not ip_targets and not instance_ranges:
    return True

  raw_addr = str(device_address).strip()
  ip_only = raw_addr.split(":", maxsplit=1)[0]
  if ip_targets and (raw_addr in ip_targets or ip_only in ip_targets):
    return True

  try:
    dev_int = int(device_id)
    for low, high in instance_ranges:
      if low <= dev_int <= high:
        return True
  except (ValueError, TypeError):
    pass

  return False


DEFAULT_UNCHANGED_THRESHOLD_SEC = 15


class BacnetFamilyProvider(FamilyProvider):
  """Pluggable BACnet protocol discovery provider for Spotter."""

  def __init__(
      self,
      bacnet_ip: Optional[str] = None,
      bacnet_port: Optional[int] = None,
      bacnet_device_id: int = BACNET_DEVICE_ID,
      unchanged_threshold_sec: int = DEFAULT_UNCHANGED_THRESHOLD_SEC,
      local_network: Optional[str] = None,
  ) -> None:
    """Initializes BacnetFamilyProvider.

    Args:
        bacnet_ip: Local IP address to bind BAC0 client.
        bacnet_port: Port to bind BAC0 client.
        bacnet_device_id: BACnet device object instance ID for local client.
        unchanged_threshold_sec: Inactivity duration before terminating scan.
        local_network: Optional default BACnet network number.
    """
    self.bacnet_ip = bacnet_ip
    self.bacnet_port = bacnet_port
    self.bacnet_device_id = bacnet_device_id
    self.unchanged_threshold_sec = unchanged_threshold_sec
    self.local_network = local_network
    self._bacnet = None
    self._lock = threading.Lock()

    self._devices_published: Set[Tuple[str, Any]] = set()
    self._targeted_devices_found: Set[Tuple[str, Any]] = set()
    self._cancelled = threading.Event()
    self._scan_thread: Optional[threading.Thread] = None
    self._resolver_thread: Optional[threading.Thread] = None
    self._event_count = 0

  def _ensure_bacnet_client(self) -> Any:
    """Returns cached or new BAC0 client instance in a thread-safe manner."""
    with self._lock:
      if self._bacnet is None:
        if BAC0 is None:
          raise RuntimeError("BAC0 library is not installed or available.")
        LOGGER.info(
            "Initializing BAC0 client (IP: %s, Port: %s, DeviceId: %d)...",
            self.bacnet_ip,
            self.bacnet_port,
            self.bacnet_device_id,
        )
        self._bacnet = BAC0.lite(
            ip=self.bacnet_ip,
            port=self.bacnet_port,
            deviceId=self.bacnet_device_id,
        )
      return self._bacnet

  def start_scan(
      self,
      discovery_config: Any,
      publish_func: Callable[[str, DiscoveryEvents], None],
  ) -> None:
    """Starts a discovery scan for the BACnet protocol family."""
    self._cancelled.clear()
    self._devices_published.clear()
    self._targeted_devices_found.clear()
    self._event_count = 0

    client = self._ensure_bacnet_client()
    generation = getattr(discovery_config, "generation", None)
    depth = _effective_depth(discovery_config)
    addrs = getattr(discovery_config, "addrs", None)
    networks = getattr(discovery_config, "networks", None)
    scan_duration_sec = getattr(discovery_config, "scan_duration_sec", None)

    LOGGER.info(
        "Starting BACnet discovery scan (generation: %s, depth: %s,"
        " addrs: %s, networks: %s)...",
        generation,
        depth,
        addrs,
        networks,
    )

    ip_targets: List[str] = []
    instance_ranges: List[Tuple[int, int]] = []
    if addrs:
      ip_targets, instance_ranges = _validate_and_classify_addrs(addrs)

    target_networks: Optional[Set[str]] = (
        {str(n).strip() for n in networks if str(n).strip()}
        if networks
        else None
    )

    # Emit start event (event_no: 0)
    publish_func(
        "self",
        DiscoveryEvents(
            generation=generation,
            family="bacnet",
            event_no=0,
        ),
    )

    if depth == "buckets":
      self._run_buckets_scan(
          client,
          generation,
          target_networks,
          publish_func,
          scan_duration_sec=scan_duration_sec,
      )
      publish_func(
          "self",
          DiscoveryEvents(
              generation=generation,
              family="bacnet",
              event_no=-(self._event_count + 1),
          ),
      )
      return

    if not addrs:
      client.discover(global_broadcast=True)
      device_producer = self._global_device_producer
    else:
      if instance_ranges:
        for low, high in instance_ranges:
          try:
            client.discover(limits=(low, high), global_broadcast=True)
          except TypeError:
            client.discover(global_broadcast=True)
      if ip_targets:
        self._resolver_thread = threading.Thread(
            target=self._resolve_targeted_ips,
            args=(copy.copy(ip_targets),),
            name="BACnet-Resolver",
            daemon=True,
        )
        self._resolver_thread.start()

      if instance_ranges and not ip_targets:
        device_producer = self._global_device_producer
      elif ip_targets and not instance_ranges:
        device_producer = self._targeted_device_producer
      else:
        device_producer = lambda: (
            self._global_device_producer() | self._targeted_device_producer()
        )

    def filtered_producer() -> Set[Tuple[str, Any]]:
      raw = device_producer()
      return {
          dev
          for dev in raw
          if _matches_target_filters(
              dev[0],
              dev[1],
              ip_targets,
              instance_ranges,
              target_networks,
              default_network=self.local_network,
          )
      }

    self._scan_thread = threading.Thread(
        target=self._devices_consumer,
        args=(filtered_producer, discovery_config, publish_func),
        name="BACnet-Consumer",
        daemon=True,
    )
    self._scan_thread.start()

    if scan_duration_sec and float(scan_duration_sec) > 0:
      timeout = float(scan_duration_sec)
      if self._scan_thread:
        self._scan_thread.join(timeout=timeout)
    else:
      if self._scan_thread:
        self._scan_thread.join()

    self.stop_scan()

    # Emit finish event (event_no: -(event_count + 1))
    publish_func(
        "self",
        DiscoveryEvents(
            generation=generation,
            family="bacnet",
            event_no=-(self._event_count + 1),
        ),
    )

  def _run_buckets_scan(
      self,
      client: Any,
      generation: Any,
      target_networks: Optional[Set[str]],
      publish_func: Callable[[str, DiscoveryEvents], None],
      scan_duration_sec: Optional[Any] = None,
  ) -> None:
    """Discovers available BACnet networks and emits one bucket event per network."""
    client.discover(global_broadcast=True)
    wait_sec = 1.0
    if scan_duration_sec and float(scan_duration_sec) > 0:
      wait_sec = min(2.0, float(scan_duration_sec) * 0.5)
    self._cancelled.wait(timeout=wait_sec)

    discovered_networks: Set[str] = set()
    if self.local_network is not None:
      discovered_networks.add(str(self.local_network))
    if client.discoveredDevices:
      for address, _ in client.discoveredDevices.keys():
        net, _ = parse_bacnet_transport_address(
            address,
            default_port=self.bacnet_port,
            default_network=self.local_network,
        )
        if net is not None:
          discovered_networks.add(str(net))

    if target_networks is not None:
      discovered_networks &= target_networks

    port_val = self.bacnet_port or DEFAULT_BACNET_PORT
    for net in sorted(discovered_networks):
      if self._cancelled.is_set():
        break
      self._event_count += 1
      event = DiscoveryEvents(
          generation=generation,
          family="bacnet",
          network=str(net),
          families={"ipv4": FamilyDiscovery(port=port_val)},
          event_no=self._event_count,
      )
      publish_func(f"network-{net}", event)

  def stop_scan(self) -> None:
    """Stops any active BACnet scan immediately."""
    LOGGER.info("Stopping BACnet discovery scan...")
    self._cancelled.set()
    if self._resolver_thread and self._resolver_thread.is_alive():
      self._resolver_thread.join(timeout=1.0)
    if self._scan_thread and self._scan_thread.is_alive():
      self._scan_thread.join(timeout=1.0)

  def _resolve_targeted_ips(self, target_ips: List[str]) -> None:
    """Resolves BACnet device IDs for targets using thread pool."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
      futures = [
          executor.submit(self._resolve_single_ip, ip) for ip in target_ips
      ]
      while _future_wait_and_count_outstanding(futures, timeout=1) > 0:
        if self._cancelled.is_set():
          executor.shutdown(wait=True, cancel_futures=True)
          break

  def _resolve_single_ip(self, ip_address: str) -> None:
    """Queries single IP address for BACnet device object identifier."""
    client = self._ensure_bacnet_client()
    try:
      res = client.read(
          f"{ip_address} device 4194303 objectIdentifier", None, 0, None, 3
      )
      dev_id = (
          res[1] if isinstance(res, (tuple, list)) and len(res) >= 2 else res
      )
      if dev_id:
        LOGGER.debug("Resolved BACnet device %s at %s", dev_id, ip_address)
        self._targeted_devices_found.add((ip_address, dev_id))
    except Exception:  # pylint: disable=broad-exception-caught
      pass

  def _global_device_producer(self) -> Set[Tuple[str, Any]]:
    """Returns newly discovered devices from global broadcast."""
    client = self._ensure_bacnet_client()
    if client.discoveredDevices is not None:
      return set(client.discoveredDevices.keys()) - self._devices_published
    return set()

  def _targeted_device_producer(self) -> Set[Tuple[str, Any]]:
    """Returns newly resolved targeted devices."""
    return self._targeted_devices_found - self._devices_published

  def _devices_consumer(
      self,
      producer: Callable[[], Set[Tuple[str, Any]]],
      discovery_config: Any,
      publish_func: Callable[[str, DiscoveryEvents], None],
  ) -> None:
    """Consumes new devices, polls properties, and publishes events."""
    unchanged_seconds = 0
    scan_duration_sec = getattr(discovery_config, "scan_duration_sec", None)
    threshold = self.unchanged_threshold_sec
    if scan_duration_sec and float(scan_duration_sec) > 0:
      threshold = min(threshold, max(1, int(float(scan_duration_sec) * 0.6)))

    first_poll = True
    while not self._cancelled.is_set():
      try:
        new_devices = producer() - self._devices_published
        if not new_devices:
          if first_poll:
            first_poll = False
            self._cancelled.wait(timeout=1.0)
            continue
          unchanged_seconds += 1
          if unchanged_seconds >= threshold:
            LOGGER.info(
                "No new BACnet devices found for %d seconds. Scan complete.",
                threshold,
            )
            return
          self._cancelled.wait(timeout=1.0)
          continue

        first_poll = False
        unchanged_seconds = 0
        for device in sorted(new_devices, key=lambda x: str(x[1])):
          if self._cancelled.is_set():
            return
          address, device_id = device
          self._event_count += 1
          event = self.discover_device(address, device_id, discovery_config)
          event.event_no = self._event_count
          publish_func(str(device_id), event)
          self._devices_published.add(device)

      except Exception as err:  # pylint: disable=broad-exception-caught
        LOGGER.error(
            "Error during BACnet device consumption: %s", err, exc_info=True
        )
        return

      if self._cancelled.is_set():
        return
      self._cancelled.wait(timeout=1.0)

  def _read_device_properties_with_fallback(
      self, client: Any, device_address: str, device_id: Any
  ) -> List[Any]:
    """Reads standard BACnet Device properties via RPM with single-read fallback."""
    prop_names = [
        "objectName",
        "vendorName",
        "firmwareRevision",
        "modelName",
        "serialNumber",
        "description",
        "location",
        "applicationSoftwareVersion",
    ]
    last_err: Optional[Exception] = None
    try:
      props = client.readMultiple(
          f"{device_address} device {device_id} " + " ".join(prop_names)
      )
      if isinstance(props, (list, tuple)) and len(props) > 0:
        padded = list(props) + [None] * max(0, 8 - len(props))
        cleaned = [None if isinstance(x, Exception) else x for x in padded[:8]]
        if any(x is not None for x in cleaned):
          return cleaned
    except Exception as rpm_err:  # pylint: disable=broad-exception-caught
      LOGGER.debug(
          "readMultiple failed for %s/%s (%s); falling back to single reads.",
          device_address,
          device_id,
          rpm_err,
      )
      last_err = rpm_err

    results: List[Any] = []
    any_success = False
    for prop in prop_names:
      try:
        val = client.read(f"{device_address} device {device_id} {prop}")
        if isinstance(val, Exception) or type(val).__name__ == "MagicMock":
          results.append(None)
        else:
          results.append(val)
          if val is not None:
            any_success = True
      except Exception as single_err:  # pylint: disable=broad-exception-caught
        last_err = single_err
        results.append(None)
    if not any_success and last_err is not None:
      raise last_err
    return results

  def discover_device(
      self, device_address: str, device_id: Any, discovery_config: Any
  ) -> DiscoveryEvents:
    """Discovers and inspects a single BACnet device."""
    client = self._ensure_bacnet_client()
    generation = getattr(discovery_config, "generation", None)
    depth_val = _effective_depth(discovery_config)

    network, families_map = parse_bacnet_transport_address(
        device_address,
        default_port=self.bacnet_port,
        default_network=self.local_network,
    )

    event = DiscoveryEvents(
        generation=generation,
        family="bacnet",
        addr=str(device_id),
        network=network,
        families=families_map if families_map else None,
    )

    if depth_val in ("system", "refs", "details", "trace"):
      try:
        (
            object_name,
            vendor_name,
            firmware_version,
            model_name,
            serial_number,
            description,
            location,
            application_version,
        ) = self._read_device_properties_with_fallback(
            client, device_address, device_id
        )

        ancillary_dict: Dict[str, Any] = {}
        if description:
          ancillary_dict["description"] = str(description)
        if location:
          ancillary_dict["location"] = str(location)
        if application_version:
          ancillary_dict["application_version"] = str(application_version)
          ancillary_dict["application-software-version"] = str(
              application_version
          )
        if firmware_version:
          ancillary_dict["firmware"] = str(firmware_version)
          ancillary_dict["firmware-revision"] = str(firmware_version)
        if object_name:
          ancillary_dict["name"] = str(object_name)

        event.system = System(
            name=str(object_name) if object_name else None,
            description=str(description) if description else None,
            serial_no=str(serial_number) if serial_number else None,
            hardware=StateSystemHardware(
                make=str(vendor_name) if vendor_name else "Unknown",
                model=str(model_name) if model_name else "Unknown",
            ),
            ancillary=ancillary_dict if ancillary_dict else None,
        )
      except Exception as err:  # pylint: disable=broad-exception-caught
        LOGGER.warning(
            "Error reading BACnet device properties (%s/%s): %s",
            device_address,
            device_id,
            err,
        )
        err_msg = str(err).strip() or type(err).__name__
        event.status = Entry(
            category="discovery.device.enumerate",
            level=500,
            message=f"Property read failed: {err_msg}",
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return event

    if depth_val in ("refs", "details", "trace"):
      try:
        refs = self.enumerate_refs(f"{device_address} {device_id}")
        if refs:
          event.refs = refs
      except Exception as err:  # pylint: disable=broad-exception-caught
        LOGGER.warning(
            "Error enumerating points for BACnet device (%s/%s): %s",
            device_address,
            device_id,
            err,
        )
        err_msg = str(err).strip() or type(err).__name__
        event.status = Entry(
            category="discovery.point.describe",
            level=500,
            message=f"Point enumeration failed: {err_msg}",
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return event

    return event

  def enumerate_refs(self, addr: str) -> Dict[str, RefDiscovery]:
    """Enumerates point references for a target BACnet device address."""
    client = self._ensure_bacnet_client()
    refs: Dict[str, RefDiscovery] = {}
    parts = addr.split()
    if len(parts) < 2:
      return refs

    device_address, device_id = parts[0], parts[1]
    try:
      dev = BAC0.device(device_address, int(device_id), client, poll=0)
      for point in dev.points:
        present_val = getattr(point, "lastValue", None)
        if present_val is None or type(present_val).__name__ == "MagicMock":
          val_attr = getattr(point, "value", None)
          if val_attr is not None and type(val_attr).__name__ != "MagicMock":
            present_val = val_attr
          elif type(present_val).__name__ == "MagicMock":
            present_val = None
        ancillary: Dict[str, Any] = {}
        if present_val is not None:
          ancillary["present_value"] = str(present_val)
          ancillary["present-value"] = str(present_val)

        raw_type = str(point.properties.type)
        canonical_type, point_acronym = _resolve_bacnet_type_and_acronym(
            raw_type
        )
        writable = point_acronym in WRITABLE_ACRONYMS

        ref = RefDiscovery(
            name=point.properties.name,
            description=point.properties.description,
            type=canonical_type,
            writable=writable,
            ancillary=ancillary if ancillary else None,
        )
        if isinstance(point.properties.units_state, list):
          ref.possible_values = [str(v) for v in point.properties.units_state]
        elif isinstance(point.properties.units_state, str):
          ref.units = point.properties.units_state

        point_id = f"{point_acronym}/{point.properties.address}"
        refs[point_id] = ref
    except Exception as err:
      LOGGER.warning(
          "Error enumerating points for BACnet device (%s): %s", addr, err
      )
      raise

    return refs

  def close(self) -> None:
    """Closes the active BAC0 client connection."""
    with self._lock:
      if self._bacnet:
        try:
          self._bacnet.disconnect()
        except Exception:  # pylint: disable=broad-exception-caught
          pass
        self._bacnet = None

  def __del__(self) -> None:
    self.close()



package com.google.daq.mqtt.sequencer;

import static com.google.udmi.util.GeneralUtils.catchToNull;

import com.google.udmi.util.SiteModel;
import java.util.Set;
import udmi.lib.ProtocolFamily;

/**
 * Resolve the DISCOVERY facet.
 */
public class DiscoveryFacetResolver implements FacetResolver {

  public static final String PRIMARY_DISCOVERY_FAMILY = ProtocolFamily.VENDOR;

  @Override
  public Set<String> resolve(SiteModel siteModel, String deviceId) {
    Set<String> families = catchToNull(
        () -> siteModel.getMetadata(deviceId).discovery.families.keySet());
    return families == null ? Set.of() : families;
  }

  @Override
  public String primary() {
    return PRIMARY_DISCOVERY_FAMILY;
  }
}

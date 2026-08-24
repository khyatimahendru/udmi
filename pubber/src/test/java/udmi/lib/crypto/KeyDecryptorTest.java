package udmi.lib.crypto;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import org.junit.BeforeClass;
import org.junit.Test;
import udmi.lib.base.UdmiException;

/**
 * Unit tests for KeyDecryptor envelope encryption and decryption.
 */
public class KeyDecryptorTest {

  private static KeyPair keyPair;

  /**
   * Initializes RSA keypair for testing.
   */
  @BeforeClass
  public static void setUp() throws Exception {
    KeyPairGenerator kpg = KeyPairGenerator.getInstance("RSA");
    kpg.initialize(2048);
    keyPair = kpg.generateKeyPair();
  }

  @Test
  public void testRsaOaepEncryptionDecryptionRoundtrip() {
    byte[] testKeyBytes = "TEST-PRIVATE-KEY-BYTES-12345".getBytes();
    String encryptedPayloadJson = KeyDecryptor.encrypt(testKeyBytes, keyPair.getPublic(), "RS256");
    assertNotNull(encryptedPayloadJson);
    assertTrue(encryptedPayloadJson.contains("RSA-OAEP-256"));

    byte[] decryptedBytes = KeyDecryptor.decrypt(encryptedPayloadJson, keyPair.getPrivate());
    assertArrayEquals(testKeyBytes, decryptedBytes);
  }

  @Test
  public void testPlaintextPayloadFallback() {
    byte[] testKeyBytes = "PLAINTEXT-KEY-BYTES-67890".getBytes();
    String plaintextPayloadJson = KeyDecryptor.makePlaintextPayload(testKeyBytes, "RS256");
    assertNotNull(plaintextPayloadJson);

    byte[] decryptedBytes = KeyDecryptor.decrypt(plaintextPayloadJson, null);
    assertArrayEquals(testKeyBytes, decryptedBytes);
  }

  @Test(expected = UdmiException.class)
  public void testCorruptCiphertextThrowsUdmiException() {
    String badPayload = "{\"key_format\":\"RS256\",\"encryption\":{"
        + "\"algorithm\":\"RSA-OAEP-256\",\"ciphertext\":\"bm90LWEtdmFsaWQtY2lwaGVydGV4dA==\"}}";
    KeyDecryptor.decrypt(badPayload, keyPair.getPrivate());
  }
}

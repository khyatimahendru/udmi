package udmi.lib.crypto;

import static com.google.udmi.util.JsonUtil.asMap;
import static com.google.udmi.util.JsonUtil.stringify;

import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import udmi.lib.base.UdmiException;
import udmi.schema.Category;

/**
 * Generic Asymmetric Envelope Encryptor/Decryptor for UDMI key rotation.
 * Supports RSA-OAEP-256 envelope encryption as well as plaintext fallback.
 */
public class KeyDecryptor {

  public static final String RSA_OAEP_256 = "RSA-OAEP-256";
  private static final String RSA_OAEP_TRANSFORMATION = "RSA/ECB/OAEPWithSHA-256AndMGF1Padding";

  /**
   * Decrypts an incoming credentials JSON payload using the device's active private key.
   *
   * @param payloadJson The raw JSON payload received in the _iot_endpoint_credentials blob.
   * @param activePrivateKey The active private key currently in use by the device.
   * @return The decrypted private key bytes in PKCS#8 format.
   */
  @SuppressWarnings("unchecked")
  public static byte[] decrypt(String payloadJson, PrivateKey activePrivateKey) {
    try {
      Map<String, Object> map = asMap(payloadJson);
      if (map == null) {
        throw new IllegalArgumentException("Invalid empty JSON payload");
      }

      if (map.containsKey("encryption")) {
        Map<String, Object> encMap = (Map<String, Object>) map.get("encryption");
        String algorithm = (String) encMap.get("algorithm");
        String ciphertext = (String) encMap.get("ciphertext");

        if (RSA_OAEP_256.equalsIgnoreCase(algorithm) || "RSA-OAEP".equalsIgnoreCase(algorithm)) {
          if (activePrivateKey == null) {
            throw new IllegalStateException("Active private key required to decrypt envelope");
          }
          return decryptRsaOaep256(Base64.getDecoder().decode(ciphertext), activePrivateKey);
        } else {
          throw new UnsupportedOperationException("Unsupported encryption algorithm: " + algorithm);
        }
      }

      // Plaintext fallback (lab / test environments)
      if (map.containsKey("key_data")) {
        String keyData = (String) map.get("key_data");
        return Base64.getDecoder().decode(keyData);
      }

      throw new IllegalArgumentException("Payload contains neither 'encryption' nor 'key_data'");
    } catch (Exception e) {
      throw new UdmiException(Category.BLOBSET_BLOB_PARSE,
          "Failed to decrypt credentials payload: " + e.getMessage(), e);
    }
  }

  /**
   * Encrypts private key bytes into an envelope JSON payload using a target public key.
   *
   * @param privateKeyBytes Raw PKCS#8 bytes to encrypt.
   * @param targetPublicKey Target public key (e.g. device's current public key).
   * @param keyFormat Format identifier (e.g. RS256).
   * @return JSON string representing the encrypted envelope.
   */
  public static String encrypt(byte[] privateKeyBytes, PublicKey targetPublicKey,
      String keyFormat) {
    try {
      byte[] ciphertext = encryptRsaOaep256(privateKeyBytes, targetPublicKey);
      String ciphertextBase64 = Base64.getEncoder().encodeToString(ciphertext);

      Map<String, Object> map = Map.of(
          "key_format", keyFormat,
          "encryption", Map.of(
              "algorithm", RSA_OAEP_256,
              "ciphertext", ciphertextBase64
          )
      );
      return stringify(map);
    } catch (Exception e) {
      throw new RuntimeException("Failed to encrypt credentials payload", e);
    }
  }

  /**
   * Helper to construct a plaintext payload for lab/test use.
   */
  public static String makePlaintextPayload(byte[] privateKeyBytes, String keyFormat) {
    String keyDataBase64 = Base64.getEncoder().encodeToString(privateKeyBytes);
    Map<String, Object> map = Map.of(
        "key_format", keyFormat,
        "key_data", keyDataBase64
    );
    return stringify(map);
  }

  private static byte[] decryptRsaOaep256(byte[] ciphertext, PrivateKey privateKey)
      throws Exception {
    Cipher cipher = Cipher.getInstance(RSA_OAEP_TRANSFORMATION);
    OAEPParameterSpec oaepParams = new OAEPParameterSpec(
        "SHA-256", "MGF1", new MGF1ParameterSpec("SHA-256"), PSource.PSpecified.DEFAULT);
    cipher.init(Cipher.DECRYPT_MODE, privateKey, oaepParams);
    return cipher.doFinal(ciphertext);
  }

  private static byte[] encryptRsaOaep256(byte[] plaintext, PublicKey publicKey)
      throws Exception {
    Cipher cipher = Cipher.getInstance(RSA_OAEP_TRANSFORMATION);
    OAEPParameterSpec oaepParams = new OAEPParameterSpec(
        "SHA-256", "MGF1", new MGF1ParameterSpec("SHA-256"), PSource.PSpecified.DEFAULT);
    cipher.init(Cipher.ENCRYPT_MODE, publicKey, oaepParams);
    return cipher.doFinal(plaintext);
  }
}

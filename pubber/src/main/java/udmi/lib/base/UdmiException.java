package udmi.lib.base;

/**
 * Container for UDMI-specific exceptions.
 */
public class UdmiException {

  /**
   * Exception thrown when a blob cannot be parsed.
   */
  public static class BlobParseException extends RuntimeException {
    public BlobParseException(String message) {
      super(message);
    }
  }


  /**
   * Exception thrown when there is a hash mismatch.
   */
  public static class HashMismatchException extends RuntimeException {
    public HashMismatchException(String message) {
      super(message);
    }
  }

  /**
   * Exception thrown when a blob is incompatible.
   */
  public static class BlobIncompatibleException extends RuntimeException {
    public BlobIncompatibleException(String message) {
      super(message);
    }
  }

  public static class PayloadTooBigException extends RuntimeException {
    public PayloadTooBigException(String message) {
      super(message);
    }
  }

  public static class BlobApplyFailureException extends RuntimeException {
    public BlobApplyFailureException(String message) {
      super(message);
    }
  }

  public static class BlobAbortException extends RuntimeException {
    public BlobAbortException(String message) {
      super(message);
    }
  }

  public static class BlobRollbackException extends RuntimeException {
    public BlobRollbackException(String message) {
      super(message);
    }
  }
}

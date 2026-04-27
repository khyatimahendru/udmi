package daq.pubber.impl.host;

import static com.google.udmi.util.JsonUtil.safeSleep;
import static java.lang.String.format;

import java.io.File;
import java.util.Map;
import java.util.function.Consumer;
import org.apache.commons.io.FileUtils;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.ObjectId;
import org.eclipse.jgit.lib.Repository;
import udmi.lib.base.UdmiException.BlobAbortException;
import udmi.lib.base.UdmiException.BlobApplyFailureException;
import udmi.lib.base.UdmiException.BlobIncompatibleException;
import udmi.lib.base.UdmiException.BlobRollbackException;

/**
 * Mock emulator for Git modules used in OTA updates.
 */
public class MockGitModuleEmulator {

  private static final String VERSION = "version";
  private static final String SIMULATE_BEHAVIOR = "simulate";
  private static final String PAYLOAD_INCOMPATIBLE = "incompatible";

  private final File repoDir;
  private final Consumer<String> infoLogger;
  private final Consumer<String> noticeLogger;
  private final Consumer<String> errorLogger;
  private boolean inMemoryFallback = false;

  /**
   * Creates a new instance of MockGitModuleEmulator.
   *
   * @param softwareModuleDir The directory for the software module.
   * @param infoLogger        Logger for info messages.
   * @param noticeLogger      Logger for notice messages.
   * @param errorLogger       Logger for error messages.
   */
  public MockGitModuleEmulator(String softwareModuleDir, Consumer<String> infoLogger,
      Consumer<String> noticeLogger, Consumer<String> errorLogger) {
    this.repoDir = new File(softwareModuleDir);
    this.infoLogger = infoLogger;
    this.noticeLogger = noticeLogger;
    this.errorLogger = errorLogger;
  }

  /**
   * Initializes the module for OTA updates.
   */
  public void initialize() {
    try {
      if (repoDir.exists()) {
        FileUtils.deleteDirectory(repoDir);
      }
      if (!repoDir.mkdirs()) {
        throw new RuntimeException("Failed to create source directory");
      }

      infoLogger.accept(format("Initializing mock JGit module in %s", repoDir.getAbsolutePath()));

      try (Git git = Git.init().setDirectory(repoDir).call()) {
        // Create v1
        File versionFile = new File(repoDir, "version.txt");
        FileUtils.writeStringToFile(versionFile, "v1", "UTF-8");
        git.add().addFilepattern(".").call();
        git.commit().setMessage("v1").setAuthor("Pubber", "pubber@udmi.io").call();
        git.tag().setName("v1").call();

        // Create v2
        FileUtils.writeStringToFile(versionFile, "v2", "UTF-8");
        git.add().addFilepattern(".").call();
        git.commit().setMessage("v2").setAuthor("Pubber", "pubber@udmi.io").call();
        git.tag().setName("v2").call();

        infoLogger.accept("Isolated JGit repo initialized successfully.");
      } catch (Exception e) {
        infoLogger.accept("JGit execution failed. Falling back to abstract in-memory logic.");
        inMemoryFallback = true;
      }
    } catch (Exception e) {
      errorLogger.accept("While initializing isolated repo: " + e.getMessage());
    }
  }

  /**
   * Handles an OTA update with the given payload.
   *
   * @param payload The update payload (e.g., commit hash).
   */
  public void updateTo(String payload) {
    infoLogger.accept(format("Decoded payload: %s", payload));

    Map<String, Object> payloadMap = com.google.udmi.util.JsonUtil.asMap(payload);
    String version = (String) payloadMap.get(VERSION);
    String simulateBehavior = (String) payloadMap.get(SIMULATE_BEHAVIOR);

    if (PAYLOAD_INCOMPATIBLE.equals(simulateBehavior)) {
      safeSleep(2000);
      throw new BlobIncompatibleException("Hardware incompatible");
    }

    if ("apply_failure".equals(simulateBehavior)) {
      safeSleep(2000);
      throw new BlobApplyFailureException("Simulated apply failure");
    }

    if ("abort".equals(simulateBehavior)) {
      safeSleep(2000);
      throw new BlobAbortException("Simulated abort");
    }

    if ("rollback".equals(simulateBehavior)) {
      safeSleep(2000);
      throw new BlobRollbackException("Simulated rollback");
    }

    if (version == null) {
      throw new RuntimeException("Missing version in JSON payload");
    }
    String commitHash = version.trim();
    infoLogger.accept(format("Triggering mock OTA update to commit %s", commitHash));

    if (inMemoryFallback) {
      infoLogger.accept("Simulating OTA update delay in-memory...");
      safeSleep(2000);
      noticeLogger.accept("Mock OTA update completed abstractly.");
      return;
    }

    try (Git git = Git.open(repoDir)) {
      infoLogger.accept("Simulating OTA update delay...");
      safeSleep(2000);
      git.checkout().setName(commitHash).call();
      noticeLogger.accept("Mock OTA update completed successfully.");
    } catch (Exception e) {
      throw new RuntimeException("JGit checkout operation failed", e);
    }
  }

  /**
   * Retrieves the current commit hash (or fallback state) of the managed module.
   */
  public String getModuleVersion() {
    if (inMemoryFallback || !repoDir.exists()) {
      return "unknown";
    }

    try (Git git = Git.open(repoDir)) {
      Repository repository = git.getRepository();
      ObjectId head = repository.resolve("HEAD");
      return head != null ? git.describe().setTarget(head).call() : "unknown";
    } catch (Exception e) {
      errorLogger.accept("Failed to resolve module version via JGit: " + e.getMessage());
      return "unknown";
    }
  }
}

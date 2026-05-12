package com.google.udmi.util;

import java.util.Arrays;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.params.SetParams;

/**
 * Utility class for distributed coordination across multiple pods using Redis.
 * Implements a "Lock and Loop" pattern to debounce requests and ensure mutual exclusion per key.
 */
public class RedisDistributedLock {

  private static final Logger LOGGER = LoggerFactory.getLogger(RedisDistributedLock.class);
  private static final String REDIS_HOST = System.getenv().getOrDefault("REDIS_HOST", "localhost");
  private static final int REDIS_PORT = 6379;
  private static final int DEFAULT_LOCK_EXPIRE_SECONDS = 3600; // 1 hour max lock
  private static final int PENDING_EXPIRE_SECONDS = 24 * 3600; // 24 hours
  private static final JedisPool jedisPool = new JedisPool(REDIS_HOST, REDIS_PORT);

  /**
   * Executes the given task exclusively for the given key, ensuring that only the latest
   * request is processed if multiple arrive concurrently.
   *
   * @param key  The unique identifier for the lock (e.g., repoId).
   * @param task The work to be executed safely.
   */
  public static void executeWithLock(String key, Runnable task) {
    String lockKey = "lock_" + key;
    String pendingKey = "pending_request_" + key;
    String requestId = UUID.randomUUID().toString();

    try (Jedis jedis = jedisPool.getResource()) {
      jedis.setex(pendingKey, PENDING_EXPIRE_SECONDS, requestId);

      String podId = UUID.randomUUID().toString();
      String acquired = jedis.set(lockKey, podId,
          SetParams.setParams().nx().ex(DEFAULT_LOCK_EXPIRE_SECONDS));
      if (acquired == null) {
        LOGGER.info("Another process is handling {}. Skipping.", key);
        return; // Lock not acquired, another pod will pick up the latest request
      }

      try {
        while (true) {
          String processingId = jedis.get(pendingKey);
          LOGGER.info("Processing {} for request {}", key, processingId);

          try {
            task.run();
          } catch (Exception e) {
            LOGGER.error("Error processing task for {}", key, e);
          }

          // Atomically check if the pending request has changed. If not, delete lock and exit.
          // If it has changed, keep the lock and loop again to process the new request.
          String releaseScript = "if redis.call('get', KEYS[1]) == ARGV[1] and redis.call('get', KEYS[2]) == ARGV[2] then "
              + "redis.call('del', KEYS[2]); return 1 else return 0 end";

          Object result = jedis.eval(releaseScript, Arrays.asList(pendingKey, lockKey),
              Arrays.asList(processingId, podId));

          if (Long.valueOf(1).equals(result)) {
            break; // Lock successfully deleted, no new requests
          }
        }
      } catch (Exception e) {
        // In case of unexpected Redis or infrastructure error, safely release lock
        LOGGER.error("Unexpected error in lock loop for {}", key, e);
        String safeRelease = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end";
        jedis.eval(safeRelease, Arrays.asList(lockKey), Arrays.asList(podId));
        throw e;
      }
    }
  }
}

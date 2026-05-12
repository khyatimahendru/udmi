package com.google.daq.mqtt.registrar;

import static org.junit.Assert.assertTrue;

import com.google.udmi.util.RedisDistributedLock;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

public class RegistrarServiceTest {

  private boolean isRedisAvailable() {
    try (JedisPool pool = new JedisPool("localhost", 6379);
         Jedis jedis = pool.getResource()) {
      return "PONG".equals(jedis.ping());
    } catch (Exception e) {
      return false;
    }
  }

  @Test
  public void testConcurrencyAndScaling() throws InterruptedException {
    if (!isRedisAvailable()) {
      System.out.println("Skipping testConcurrencyAndScaling because Redis is not available locally.");
      return;
    }

    int numThreads = 10;
    ExecutorService executor = Executors.newFixedThreadPool(numThreads);
    CountDownLatch latch = new CountDownLatch(numThreads);
    AtomicInteger executionCount = new AtomicInteger(0);

    String repoId = "test-repo-123";

    for (int i = 0; i < numThreads; i++) {
      executor.submit(() -> {
        try {
          RedisDistributedLock.executeWithLock(repoId, () -> {
            executionCount.incrementAndGet();
            try {
              Thread.sleep(100);
            } catch (InterruptedException e) {
              Thread.currentThread().interrupt();
            }
          });
        } finally {
          latch.countDown();
        }
      });
    }

    assertTrue("Threads did not complete in time", latch.await(10, TimeUnit.SECONDS));

    int count = executionCount.get();
    assertTrue("Execution count should be > 0 and < " + numThreads + ", was " + count, count > 0 && count < numThreads);

    executor.shutdown();
  }
}

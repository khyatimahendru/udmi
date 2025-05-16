package com.google.udmi.util;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SchemaValidatorsConfig;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;

import java.util.HashSet;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;
import org.junit.runners.Parameterized.Parameters;
import org.skyscreamer.jsonassert.JSONAssert;
import org.skyscreamer.jsonassert.JSONCompareMode;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.junit.Assert.*;

@RunWith(Parameterized.class)
public class GeneratedClassValidatorTest {

  private static final String SCHEMAS_ROOT_DIR = "/usr/local/google/home/heykhyati/Projects/udmi/schema";
  private static final String GENERATED_CODE_PACKAGE_PREFIX = "udmi.schema.";
  private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
  private static final JsonSchemaFactory SCHEMA_FACTORY = JsonSchemaFactory.getInstance(
      SpecVersion.VersionFlag.V7);

  // Helper class to hold schema info
  private static class SchemaTestData {

    final Path schemaPath;
    final String schemaFileName;
    final String className;
    final String fullyQualifiedClassName;
    final Class<?> generatedClass;
    final JsonSchema jsonSchemaValidator;

    SchemaTestData(Path schemaPath, JsonNode rawSchemaJsonNode) throws ClassNotFoundException {
      this.schemaPath = schemaPath;
      this.schemaFileName = schemaPath.getFileName().toString();

      String title =
          rawSchemaJsonNode.has("title") ? rawSchemaJsonNode.get("title").asText() : null;
      if (title != null && !title.isEmpty()) {
        this.className = title.replaceAll("[^a-zA-Z0-9]", "");
      } else {
        String baseName = schemaFileName.substring(0, schemaFileName.lastIndexOf('.'));
        this.className = Stream.of(baseName.split("[_-]"))
            .filter(s -> !s.isEmpty())
            .map(s -> s.substring(0, 1).toUpperCase() + s.substring(1).toLowerCase())
            .collect(Collectors.joining(""));
      }
      this.fullyQualifiedClassName = GENERATED_CODE_PACKAGE_PREFIX + this.className;

      try {
        this.generatedClass = Class.forName(this.fullyQualifiedClassName);
      } catch (ClassNotFoundException e) {
        throw new ClassNotFoundException(
            "Could not find generated class " + this.fullyQualifiedClassName + " for schema "
                + schemaFileName, e);
      }

      SchemaValidatorsConfig config = new SchemaValidatorsConfig();
      config.setHandleNullableField(true);
      this.jsonSchemaValidator = SCHEMA_FACTORY.getSchema(rawSchemaJsonNode, config);
    }

    @Override
    public String toString() {
      return schemaFileName + " (Class: " + className + ")";
    }
  }

  private final SchemaTestData currentSchemaData;

  public GeneratedClassValidatorTest(SchemaTestData schemaData) {
    this.currentSchemaData = schemaData;
  }

  @BeforeClass
  public static void setUpClass() {
    OBJECT_MAPPER.registerModule(new JavaTimeModule());
    OBJECT_MAPPER.configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false);
  }

  @Parameters
  public static Collection<Object[]> discoverSchemasAndClasses() throws IOException {
    List<Object[]> parameters = new ArrayList<>();
    Set<String> skipped = new HashSet<>();
    Path schemaRootDirPath = Paths.get(SCHEMAS_ROOT_DIR);

    if (!Files.exists(schemaRootDirPath) || !Files.isDirectory(schemaRootDirPath)) {
      System.err.println("ERROR: Schema root directory not found or not a directory: "
          + schemaRootDirPath.toAbsolutePath());
      throw new IOException("Schema root directory not found: " + SCHEMAS_ROOT_DIR
          + ". Cannot collect test parameters.");
    }

    try (Stream<Path> paths = Files.walk(schemaRootDirPath)) {
      paths.filter(Files::isRegularFile)
          .filter(path -> path.toString().endsWith(".json"))
          .forEach(schemaPath -> {
            System.out.println("Processing schema: " + schemaPath);
            try (InputStream schemaStream = Files.newInputStream(schemaPath)) {
              JsonNode schemaJsonNode = OBJECT_MAPPER.readTree(schemaStream);
              parameters.add(new Object[]{new SchemaTestData(schemaPath, schemaJsonNode)});
            } catch (IOException e) {
              System.err.println(
                  "WARNING: Failed to read or parse schema: " + schemaPath + " - " + e.getMessage()
                      + ". Skipping.");
              skipped.add(String.valueOf(schemaPath));
            } catch (ClassNotFoundException e) {
              System.err.println(
                  "WARNING: " + e.getMessage() + ". Skipping schema " + schemaPath.getFileName());
              skipped.add(String.valueOf(schemaPath));
            } catch (Exception e) {
              System.err.println(
                  "WARNING: Error processing schema " + schemaPath + ": " + e.getMessage()
                      + ". Skipping.");
              skipped.add(String.valueOf(schemaPath));
            }
          });
    }

    if (parameters.isEmpty()) {
      System.err.println(
          "WARNING: No valid schemas and corresponding classes found in " + SCHEMAS_ROOT_DIR +
              ". The test suite for GeneratedClassValidatorTestJUnit4Minimal will be empty.");
    }
    System.out.println("Collected " + parameters.size() + " schemas to test.");
    System.err.println("Skipped " + skipped.size() + "schemas");
    return parameters;
  }

  @Test
  public void testCanInstantiate() throws Exception {
    Object instance = currentSchemaData.generatedClass.getDeclaredConstructor().newInstance();
    assertNotNull("Instance should not be null for " + currentSchemaData.className, instance);
  }

  @Test
  public void testBasicSerializationOfEmptyObject() throws Exception {
    Object instance = currentSchemaData.generatedClass.getDeclaredConstructor().newInstance();
    String json = OBJECT_MAPPER.writeValueAsString(instance);
    assertNotNull("Serialized JSON string should not be null for " + currentSchemaData.className,
        json);
    OBJECT_MAPPER.readTree(json);
  }

  @Test
  public void testRoundTripWithMinimalValidJson() throws Exception {
    String minimalJsonPayload = "{}";

    JsonNode jsonToTest = OBJECT_MAPPER.readTree(minimalJsonPayload);
    Set<ValidationMessage> validationMessages = currentSchemaData.jsonSchemaValidator.validate(
        jsonToTest);

    if (validationMessages.isEmpty()) {
      Object deserializedInstance = OBJECT_MAPPER.readValue(minimalJsonPayload,
          currentSchemaData.generatedClass);
      assertNotNull("Deserialized instance should not be null for " + currentSchemaData.className,
          deserializedInstance);

      String reserializedJson = OBJECT_MAPPER.writeValueAsString(deserializedInstance);

      JSONAssert.assertEquals("Round trip JSON mismatch for " + currentSchemaData.className,
          minimalJsonPayload, reserializedJson, JSONCompareMode.LENIENT);
    } else {
      System.out.println(
          "INFO: Skipping roundTripWithMinimalJson for " + currentSchemaData.className +
              " because '" + minimalJsonPayload
              + "' is not valid according to its schema. Violations: " + validationMessages);
    }
  }

  @Test
  public void testEqualsAndHashCodeContractForEmptyObjects() throws Exception {
    Object instance1 = currentSchemaData.generatedClass.getDeclaredConstructor().newInstance();
    Object instance2 = currentSchemaData.generatedClass.getDeclaredConstructor().newInstance();

    assertEquals(instance1, instance1);
    assertEquals("Initial empty objects should be equal for " + currentSchemaData.className,
        instance1, instance2);
    assertEquals("Symmetric equality failed for " + currentSchemaData.className, instance2,
        instance1);
    assertEquals(
        "Hashcodes should be equal for equal empty objects in " + currentSchemaData.className,
        instance1.hashCode(), instance2.hashCode());
  }

  @Test
  public void testToStringWorks() throws Exception {
    Object instance = currentSchemaData.generatedClass.getDeclaredConstructor().newInstance();
    String toStringResult = instance.toString();
    assertNotNull("toString() should return a non-null string for " + currentSchemaData.className,
        toStringResult);
    assertTrue("toString() should not be empty for " + currentSchemaData.className,
        !toStringResult.isEmpty());
  }
}
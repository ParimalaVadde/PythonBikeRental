# COMPLETE GENERIC CODE FOR IDENTIFIERS USING MELT OPERATION
from pyspark.sql.functions import col, lit, when, struct, row_number
from pyspark.sql.window import Window
from pyspark.sql.types import StringType

print("Starting generic identifiers processing with melt operation...")

# STEP 1: Prepare relationship data with unique identifiers for melting
print("Step 1: Preparing relationship data for melting...")

# Create unique identifier for each row to handle duplicate business_entity_relationship_ids
window_spec = Window.orderBy("business_entity_relationship_id", "stg_business_entity_id", 
                            "client_vendor_id", "client_vendor_site_id", "client_ecid", 
                            "supplier_ecid", "associated_tax_ids")

transformed_relationship_unique = transformed_relationship.withColumn(
    "unique_row_id", 
    row_number().over(window_spec)
)

# Select columns for relationship identifiers
transformed_rel_identifiers = transformed_relationship_unique.select(
    col("unique_row_id"),
    col("stg_business_entity_id"),
    col("business_entity_relationship_id"),
    col("client_vendor_id"),
    col("client_vendor_site_id"),
    col("client_ecid"),
    col("supplier_ecid"),
    col("associated_tax_ids")
)

# STEP 2: Melt relationship identifiers using your melt function
print("Step 2: Melting relationship identifiers...")

# List of columns to melt for relationship identifiers
transformed_rel_identifiers_columns = ["client_vendor_id", "client_vendor_site_id", "client_ecid", "supplier_ecid", "associated_tax_ids"]

# Melt relationship identifiers
melted_rel_identifiers = utl.melt_dataframe(
    transformed_rel_identifiers,
    id_column="unique_row_id",
    columns_to_melt=transformed_rel_identifiers_columns,
    melted_column_names=("identifier_type", "identifier_value")
)

# STEP 3: Join back with relationship data to get business_entity_relationship_id
print("Step 3: Joining melted data with relationship info...")

# Join to get back the business_entity_relationship_id
transformed_rel_identifiers_final = melted_rel_identifiers.join(
    transformed_rel_identifiers.select("unique_row_id", "business_entity_relationship_id"),
    on="unique_row_id",
    how="inner"
).select(
    col("identifier_type"),
    col("identifier_value"),
    col("business_entity_relationship_id").alias("related_identifier")
).withColumn("related_identifier_source", lit("relationship"))

print(f"Relationship identifiers created: {transformed_rel_identifiers_final.count()}")

# STEP 4: Create business entity identifiers using melt
print("Step 4: Creating business entity identifiers...")

# Select columns from transformed_df for identifiers
transformed_identifiers_source = transformed_df.select(*ss.identifiers)

# Melt business entity identifiers
melted_business_identifiers = utl.melt_dataframe(
    transformed_identifiers_source,
    id_column="stg_business_entity_id",
    columns_to_melt=ss.transformed_identifiers_columns,
    melted_column_names=("identifier_type", "identifier_value")
)

# Prepare business entity identifiers
transformed_business_identifiers_final = melted_business_identifiers.select(
    col("identifier_type"),
    col("identifier_value"),
    col("stg_business_entity_id").alias("related_identifier")
).withColumn("related_identifier_source", lit("business_entity"))

print(f"Business entity identifiers created: {transformed_business_identifiers_final.count()}")

# STEP 5: Combine both sources
print("Step 5: Combining all identifiers...")

# Union both sources - no anti-join needed
transformed_identifiers = transformed_business_identifiers_final.union(transformed_rel_identifiers_final)

# Drop duplicates
transformed_identifiers = transformed_identifiers.dropDuplicates()

print(f"Total combined identifiers: {transformed_identifiers.count()}")

# STEP 6: Transform identifier types
print("Step 6: Standardizing identifier types...")

# Update identifier_type column to standardize ecid types
transformed_identifiers = transformed_identifiers.withColumn(
    "identifier_type",
    when(col("identifier_type") == "client_ecid", "ecid")
    .when(col("identifier_type") == "supplier_ecid", "ecid")
    .otherwise(col("identifier_type"))
)

# STEP 7: Add required columns
print("Step 7: Adding final columns...")

# Add is_active column
transformed_identifiers = transformed_identifiers.withColumn(
    "is_active", 
    lit(True)
)

# Generate UUID for identifier_id
transformed_identifiers = transformed_identifiers.withColumn(
    "identifier_id",
    compute_uuid_udf(struct(*[col(c) for c in transformed_identifiers.columns]))
)

# FINAL OUTPUT
print("IDENTIFIERS PROCESSING COMPLETED SUCCESSFULLY!")
print(f"Final identifier count: {transformed_identifiers.count()}")
print(f"Relationship source identifiers: {transformed_identifiers.filter(col('related_identifier_source') == 'relationship').count()}")
print(f"Business entity source identifiers: {transformed_identifiers.filter(col('related_identifier_source') == 'business_entity').count()}")

# Show final results
print("Sample of final identifiers:")
transformed_identifiers.show(20, truncate=False)

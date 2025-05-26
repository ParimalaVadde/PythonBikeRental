import sys
import boto3
import json
import hashlib
import uuid
import psycopg2
import utils as utl
import staging_schema as ss
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql.functions import col, explode, lit, when, udf, to_date, current_date
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, ArrayType, DoubleType, IntegerType, MapType
from pyspark.sql.utils import AnalysisException
from datetime import datetime
from pyspark.sql.functions import when, lit, col, explode,from_json
from pyspark.sql.functions import  concat_ws,current_timestamp
from pyspark.sql.functions import broadcast



## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)


s3 = boto3.client("s3")
#s3.download_file(s3_bucket,ssl_cert_s3_path,local_ssl_cert_path)


rds_client = boto3.client ("rds",region_name=ss.region)
rds_token = rds_client.generate_db_auth_token(
    DBHostname = ss.rds_host,
    Port = ss.rds_port,
    DBUsername = ss.db_user
    )
    
pg_connection_options = {
    "url" : f"jdbc:postgresql://{ss.rds_host}:{ss.rds_port}/{ss.db_name}?sslmode=require&sslrootcert={ss.ssl_cert_s3_path}",
    "user" : ss.db_user,
    "password" : rds_token
   # "db_table":source_table
    }

# Register the UDF
compute_uuid_udf = udf(utl.compute_uuid, StringType())


truncate = utl.truncate_tables(ss.rds_host,ss.rds_port,ss.db_name,ss.db_user,rds_token,ss.ssl_cert_s3_path)

def get_landing_data():
    try:
        # Query to fetch data
        query = "(SELECT DISTINCT * FROM sds_landing.analysis_pfd WHERE filter_employee = 'N') AS temp_table"

        # Read the query result into a Spark DataFrame
        source_df = glueContext.read.format("jdbc").options(
                dbtable=query,
                **pg_connection_options
            ).load()

        # Define UDFs for computing business entity ID and buying entity ID
        
        

        source_df = source_df.withColumn(
                        "stg_business_entity_id",
                        when(
                            col("sds_supplier_id").isNotNull(), col("sds_supplier_id")
                            ).otherwise(
                                compute_uuid_udf(concat_ws(",", col("vendor_name_cleaned")))
                            )
                            )
                

                    
        print("stg_business_entity_id column added.")


        source_df = source_df.withColumn(
                "stg_buying_entity",
            compute_uuid_udf(concat_ws(",", col("buying_entity")))
                )
                
        print("stg_buying_entity column added.")

        print("After adding the UUID columns")
        source_df.select("stg_business_entity_id").show()
        # Return the Spark DataFrame
        return source_df

    except Exception as e:
        print('Error Message is:', e)
        return None
        


def process_mapping_and_transform_data(source_df, mapping_file_path, output_data_path):
    """
    Reads a mapping file and input data, applies column transformations, and writes the transformed data to S3.
    """
    # Read the mapping file into a Glue DynamicFrame
    mapping_df = glueContext.create_dynamic_frame.from_options(
        connection_type="s3",
        connection_options={"paths": [mapping_file_path]},
        format="csv",
        format_options={"withHeader": True}
    ).toDF()

    print("Reading mapping file completed")

    # Validate mapping DataFrame
    if mapping_df.rdd.isEmpty():
        raise ValueError("The mapping DataFrame is empty. Please check the mapping file.")
    if "source_column" not in mapping_df.columns or "target_column" not in mapping_df.columns:
        raise ValueError("The mapping DataFrame does not contain the required columns: 'source_column' and 'target_column'.")

    # Initialize variables
    column_mapping = {}
    current_date = datetime.today().strftime("%Y-%m-%d")

    # Iterate through the mapping DataFrame to create the column mapping dictionary
    for row in mapping_df.collect():
        source_col = str(row["source_column"]).strip().lower()
        target_col = row["target_column"]
        column_mapping[source_col] = target_col

   # print("Column Mapping Dictionary:")
   # print(column_mapping)

    # Read the input data into a Glue DynamicFrame
    source_df.show()
    data = source_df
    print("data:", data.show())

    # Validate input DataFrame
    if data.rdd.isEmpty():
      #  raise ValueError("The input DataFrame is empty. Please check the source data.")
      print("The input DataFrame is empty. Please check the source data.")

    # Verify that all source columns exist in the input DataFrame
    # missing_columns = [col for col in column_mapping.keys() if col not in data.columns]
    # if missing_columns:
    #     raise ValueError(f"The following columns are missing in the input data: {missing_columns}")
    #  #   print("The following columns are missing in the input data",missing_columns )
        
    print("before transforming the data")

    # Rename columns in the input DataFrame using the column mapping
    transformed_df = data.select(
        [col(c).alias(column_mapping[c]) if c in column_mapping else col(c) for c in data.columns]
    )
    # Add a new column "stg_jpmc_business_entity_id" based on the condition
    transformed_df = transformed_df.withColumn(
        "stg_jpmc_business_entity_id",
        when(
            (col("client_ecid").isNotNull()) | (col("ind_jpmc") == 'Y'),
            lit("2d35a04a-5fdf-50d5-7750-c1c7621ddc33")
        ).otherwise(None)
    )
    
    print("after transforming the data")

    print("Transformed DataFrame:")
    #transformed_df.show()

    # Validate transformed DataFrame
    if transformed_df.rdd.isEmpty():
        raise ValueError("The transformed DataFrame is empty after applying column mappings.")

    # Convert the Spark DataFrame to a Glue DynamicFrame
    #transformed_dynamic_frame = DynamicFrame.fromDF(transformed_df, glueContext, "transformed_dynamic_frame")


    

    print("Transformation and writing completed")
    return transformed_df
    
    
landing_tables= get_landing_data()
#landing_tables.show()
transformed_df = process_mapping_and_transform_data(landing_tables,ss.mapping_file_path, ss.output_data_path)


def transform_dataframes(transformed_df, ss, glueContext, compute_uuid_udf, utl):
    """
    Function to transform multiple DataFrames based on the provided schemas and logic.

    Args:
        transformed_df (DataFrame): The input PySpark DataFrame.
        ss (object): An object containing schema definitions and column mappings.
        glueContext (GlueContext): The AWS Glue context.
        compute_uuid_udf (UDF): A UDF to compute UUIDs.
        utl (module): A utility module containing helper functions like `flatten_nested_json_column` and `melt_dataframe`.

    Returns:
        dict: A dictionary of transformed DataFrames.
    """
    # Flatten the JSON columns
    transformed_json_df = transformed_df.select(*ss.jsoncol)
 
    # Flatten nested JSON columns
    for column, schema in [
        ("card_revenue", ss.card_revenue_schema),
        ("card_transactions_stability", ss.card_transactions_stability),
        ("associated_people", ss.associated_people_schema),
        ("industries", ss.industries_schema),
        ("company_structure", ss.company_structure_schema),
        ("technologies", ss.technologies_schema),
    ]:
        transformed_json_df = utl.flatten_nested_json_column(transformed_json_df, column, schema)

    # Explode and process specific columns
    transformed_json_df = transformed_json_df.withColumn("associated_people__title", explode(col("associated_people__titles"))).drop("associated_people__titles")
    transformed_json_df = transformed_json_df.withColumn("associated_tax_ids", from_json(col("associated_tax_ids"), ss.associated_tax_ids_schema))
    transformed_json_df = transformed_json_df.withColumn("associated_tax_id", explode(col("associated_tax_ids"))).drop("associated_tax_ids")
    # transformed_json_df = transformed_json_df.withColumn("registered_agents", from_json(col("registered_agents"), ss.registered_agents_schema))
    # transformed_json_df = transformed_json_df.withColumn("registered_agents", explode(col("registered_agents")))
    transformed_json_df = utl.flatten_nested_json_column(
        transformed_json_df,
        "registered_agents",
        ss.registered_agents_schema,
        explode_array=False)

    transformed_json_df.show()
    
    #############################transformed_business_entity##########################################
    # Transform `transformed_business_entity`
    transformed_business_entity = transformed_df.select(
        col("stg_business_entity_id").alias("stg_business_entity_id")
    ).union(
        transformed_df.select(col("stg_payor_business_entity_id").alias("stg_business_entity_id"))
    ).union(
        transformed_df.select(col("stg_jpmc_business_entity_id").alias("stg_business_entity_id"))
    ).dropDuplicates()
    ################################################################################################
    
    
    ##########################transformed_business_entity_details###################################
    # Transform `transformed_business_entity_details`
    transformed_business_entity_details = transformed_df.select(*ss.business_entity_details).join(
        transformed_json_df.select("stg_business_entity_id", "company_structure__corporate_structure"),
        on="stg_business_entity_id",
        how="left"
    ).withColumn(
        "company_structure",
        when(col("filter_individual") == "Y", "individual").otherwise(col("company_structure__corporate_structure"))
    ).drop("filter_individual", "company_structure__corporate_structure").dropDuplicates()

    # Add additional rows to `transformed_business_entity_details`
    for additional_row in [
        transformed_df.select(
            col("stg_jpmc_business_entity_id").alias("stg_business_entity_id"),
            lit("jpmc").alias("business_entity_name"),
            lit("").alias("company_structure"),
            lit("").alias("year_incorporated"),
            lit("").alias("reported_annual_revenue")
        ),
        transformed_df.select(
            col("stg_payor_business_entity_id").alias("stg_business_entity_id"),
            col("buying_entity").alias("business_entity_name"),
            lit("").alias("company_structure"),
            lit("").alias("year_incorporated"),
            lit("").alias("reported_annual_revenue")
        )
    ]:
        transformed_business_entity_details = transformed_business_entity_details.union(additional_row)
    
    transformed_business_entity_details = transformed_business_entity_details.withColumn(
        "business_entity_details_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_business_entity_details.columns]))
    )
    
    transformed_business_entity_details.show()
    ################################################################################################
    
    
    ##########################transformed_business_contacts###################################
    transformed_json_df.select(*ss.contacts).distinct().show()
    
    
    # Transform `transformed_contacts`
    transformed_contact = transformed_json_df.select(*ss.contacts).distinct().withColumnRenamed(
        "associated_people__name", "contact_name"
    ).withColumnRenamed(
        "associated_people__title", "contact_title"
    )

    vendor_contact_df = transformed_df.select(*ss.vendor_contact).distinct()

    vendor_contact_df = vendor_contact_df.select(
        col("stg_business_entity_id"),
        col("vendor_contact_name").alias("contact_name"),
        lit(None).cast("string").alias("contact_title")
    )

    transformed_contacts = transformed_contact.unionByName(vendor_contact_df)

    transformed_contacts.show()
    transformed_contacts = transformed_contacts.withColumn(
        "business_entity_contact_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_contacts.columns]))
    )
    transformed_contacts.show()
    ################################################################################################


    ##########################business_enity_card_revenues#########################################
    # Transform `transformed_revenue`
    transformed_revenue = transformed_json_df.select(*ss.revenue).withColumnRenamed(
        "card_revenue__end_date", "end_date"
    )
    transformed_revenue = transformed_revenue.withColumn(
        "revenue_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_revenue.columns]))
    ).dropDuplicates()
    ################################################################################################
    
    
    ##########################business_entity_card_transactions_stability#######################
    # Transform `transformed_transaction_stability`
    transformed_transaction_stability = transformed_json_df.select(*ss.transaction_stability).withColumnRenamed(
        "card_transactions_stability__end_date", "end_date"
    )
    transformed_transaction_stability = transformed_transaction_stability.withColumn(
        "card_transactions_stability_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_transaction_stability.columns]))
    ).dropDuplicates()
    ################################################################################################
    
    
    ##########################business_entity_receivables_attribute#######################
    # Transform `transformed_melt_payment_profile_attribute`
    transformed_melt_payment_profile_attribute = utl.melt_dataframe(
        transformed_df.select(*ss.payment_profile),
        id_column="stg_business_entity_id",
        columns_to_melt=ss.payment_profile_columns,
        melted_column_names=("receivables_attribute_type", "receivables_attribute_value")
    )
    transformed_melt_payment_profile_attribute = transformed_melt_payment_profile_attribute.withColumn(
        "attribute_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_payment_profile_attribute.columns]))
    ).select(
        col("attribute_id"), col("stg_business_entity_id"), col("receivables_attribute_type"), col("receivables_attribute_value")
    )
    ################################################################################################
    
        
    ##########################telecommunication_address############################################
    # Transform `transformed_melt_telecommunication_address`
    transformed_melt_telecommunication_address = utl.melt_dataframe(
        transformed_df.select(*ss.telecommunication_address),
        id_column="stg_business_entity_id",
        columns_to_melt=ss.telecommunication_address_columns,
        melted_column_names=("telecommunication_address_type", "phone_number")
    ).withColumn(
        "telecommunication_address_type",
        when(col("telecommunication_address_type") == "primary_phone_number", "primary").otherwise(col("telecommunication_address_type"))
    ).withColumnRenamed(
        "stg_business_entity_id", "related_identifier"
    ).withColumn(
        "related_identifier_source", lit("business_entity")
    )
    
    transformed_melt_telecommunication_address = transformed_melt_telecommunication_address.withColumn(
        "telecommunication_address_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_telecommunication_address.columns]))
    )
    ################################################################################################
    
    
    ##########################electronic_address############################################
    # Transform `transformed_melt_electronic_address`
    transformed_melt_electronic_address = utl.melt_dataframe(
        transformed_df.select(*ss.electronic_address),
        id_column="stg_business_entity_id",
        columns_to_melt=ss.electronic_address_columns,
        melted_column_names=("electronic_address_type", "electronic_address")
    ).withColumn(
        "electronic_address_type",
        when(col("electronic_address_type") == "email", "primary").otherwise(col("electronic_address_type"))
    ).withColumnRenamed(
        "stg_business_entity_id", "related_identifier"
    ).withColumn(
        "related_identifier_source", lit("business_entity")
    )
    
    transformed_melt_electronic_address = transformed_melt_electronic_address.withColumn(
        "electronic_address_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_electronic_address.columns]))
    )
    ################################################################################################


    ##########################restrictions#########################################################
    # Transform `transformed_melt_restrictions`
    transformed_melt_restrictions = utl.melt_dataframe(
        transformed_df.select(*ss.restrictions),
        id_column="stg_business_entity_id",
        columns_to_melt=ss.restrictions_columns,
        melted_column_names=("restriction_type", "restriction_indicator")
    ).withColumnRenamed(
        "stg_business_entity_id", "related_identifier"
    ).withColumn(
        "related_identifier_source", lit("business_entity")
    )
    
    transformed_melt_restrictions = transformed_melt_restrictions.withColumn(
        "restriction_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_restrictions.columns]))
    )
    ################################################################################################
    
    
    ##########################classification#########################################################
    # Transform `transformed_melt_industry_classification`
    transformed_melt_industry_classification = utl.melt_dataframe(
        transformed_df.select(*ss.industry_classification),
        id_column="stg_business_entity_id",
        columns_to_melt=ss.industry_classification_columns,
        melted_column_names=("classification_code", "classification_description")
    ).withColumn(
        "classification_type",
        when(col("classification_code").isin("Level-1", "Level-2", "Level-3"), "bloomberg").otherwise("individual")
    )
    
    transformed_melt_industry_classification = transformed_melt_industry_classification.withColumn(
        "classification_id",
        compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_industry_classification.columns]))
    )

    ################################################################################################
    
    
	##########################characteristics#########################################################
    transformed_characteristics = transformed_df.select(*ss.characteristics)
    
    
    transformed_characteristics = transformed_characteristics.join(
    transformed_json_df.select("stg_business_entity_id", "registered_agents"),
    on="stg_business_entity_id",
    how="left"
    )

    # Perform a left join between `transformed_characteristics` and `transformed_json_df`
    transformed_melt_characteristics = utl.melt_dataframe(
    transformed_characteristics,
    id_column="stg_business_entity_id",
    columns_to_melt=ss.characteristics_columns,
    melted_column_names=("characteristic_type", "characteristic_value"))

    # Get the current date
    current_date = datetime.today().strftime("%Y-%m-%d")

    # Update the `characteristic_value` column based on the condition
    transformed_melt_characteristics = transformed_melt_characteristics.withColumn(
		"characteristic_value",
		F.when(
			F.col("characteristic_type").isin("Moody", "SP"),
			F.concat_ws(";", F.col("characteristic_type"), F.col("characteristic_value"), F.lit(current_date))
		).otherwise(F.col("characteristic_value"))
	)

    # Update the `characteristic_type` column based on the condition
    transformed_melt_characteristics = transformed_melt_characteristics.withColumn(
		"characteristic_type",
		F.when(
			F.col("characteristic_type").isin("Moody", "SP"),
			F.lit("Credit_Rating_Provider_Date")
		).otherwise(F.col("characteristic_type"))
	)
    transformed_melt_characteristics = transformed_melt_characteristics.filter(
		col("characteristic_value").isNotNull()
	)
    transformed_melt_characteristics = transformed_melt_characteristics.withColumn(
		"characteristics_id",
		compute_uuid_udf(concat_ws(",", *[col for col in transformed_melt_characteristics.columns]))
	)
    ################################################################################################
    
    
    ##########################physical_address#########################################################
    transformed_physical_address = transformed_df.select(*ss.physical_address).withColumn("physical_address_type", lit("Billing")).withColumnRenamed("stg_business_entity_id", "related_identifier").withColumn("related_identifier_source", lit("business_entity"))
    
    transformed_physical_address = transformed_physical_address.withColumn("physical_address_id",
		compute_uuid_udf(concat_ws(",", *[col for col in transformed_physical_address.columns]))
	)
    ################################################################################################
    
    
    ##########################association#########################################################
    transformed_association = transformed_df.select(*ss.association).distinct().withColumn(
        "association_name",
		when(col("ind_card_match").isin("yes","YES")  , "visa" ).otherwise(""))

    transformed_association = transformed_association.withColumn(
		"card_association_id",
		compute_uuid_udf(concat_ws(",", *[col for col in transformed_association.columns])))
    ################################################################################################

	
    ##########################spend_analysis#########################################################
    transformed_spend_analysis = transformed_df.select(*ss.spend_analysis).withColumnRenamed(
		"stg_business_entity_id", "stg_payee_business_entity_id"
	)

    # Rename the column `stg_business_entity_id` to `stg_payee_business_entity_id`
    transformed_spend_analysis = transformed_spend_analysis.withColumnRenamed(
        "stg_business_entity_id", "stg_payee_business_entity_id"
    ).withColumn(
        "analysis_conducted_dt",
        when(
            col("analysis_conducted_dt").isNotNull(),
            to_date(col("analysis_conducted_dt").substr(1, 8), "yyyyMMdd")
        )
    ).withColumn(
        "period_start_date",
        when(
            col("period_start_date").isNotNull(),
            to_date(col("period_start_date").substr(1, 8), "MMddyyyy")
        )
    ).withColumn(
        "period_end_date",
        when(
            col("period_end_date").isNotNull(),
            to_date(col("period_end_date").substr(1, 8), "MMddyyyy")
        )
    )

    transformed_spend_analysis = transformed_spend_analysis.withColumn(
		"spend_analysis_id",
		compute_uuid_udf(concat_ws(",", *[col for col in transformed_spend_analysis.columns]))
	)
    ################################################################################################

    # Return all transformed DataFrames as a dictionary
    return {
        "transformed_business_entity": transformed_business_entity,
        "transformed_business_entity_details": transformed_business_entity_details,
        "transformed_contacts": transformed_contacts,
        "transformed_revenue": transformed_revenue,
        "transformed_transaction_stability": transformed_transaction_stability,
        "transformed_melt_payment_profile_attribute": transformed_melt_payment_profile_attribute,
        "transformed_melt_telecommunication_address": transformed_melt_telecommunication_address,
        "transformed_melt_electronic_address": transformed_melt_electronic_address,
        "transformed_melt_restrictions": transformed_melt_restrictions,
        "transformed_melt_industry_classification": transformed_melt_industry_classification,
        "transformed_melt_characteristics":transformed_melt_characteristics,
        "transformed_physical_address":transformed_physical_address,
		"transformed_association":transformed_association,
		"transformed_spend_analysis":transformed_spend_analysis
    }
    


transformed_dataframes = transform_dataframes(transformed_df, ss, glueContext, compute_uuid_udf, utl)

# Access individual DataFrames
transformed_business_entity = transformed_dataframes["transformed_business_entity"]
transformed_business_entity_details = transformed_dataframes["transformed_business_entity_details"]
transformed_contacts = transformed_dataframes["transformed_contacts"]
transformed_revenue = transformed_dataframes["transformed_revenue"]
transformed_transaction_stability = transformed_dataframes["transformed_transaction_stability"]
transformed_melt_payment_profile_attribute = transformed_dataframes["transformed_melt_payment_profile_attribute"]
transformed_melt_telecommunication_address = transformed_dataframes["transformed_melt_telecommunication_address"]
transformed_melt_electronic_address = transformed_dataframes["transformed_melt_electronic_address"]
transformed_melt_restrictions = transformed_dataframes["transformed_melt_restrictions"]
transformed_melt_industry_classification = transformed_dataframes["transformed_melt_industry_classification"]
transformed_melt_characteristics = transformed_dataframes["transformed_melt_characteristics"]
transformed_physical_address = transformed_dataframes["transformed_physical_address"]
transformed_association = transformed_dataframes["transformed_association"]
transformed_spend_analysis = transformed_dataframes["transformed_spend_analysis"]





def relationship(transformed_business_entity, transformed_contacts, transformed_df):
    # Add `business_entity_role` column based on conditions
    transformed_df = transformed_df.withColumn(
        "business_entity_role",
        when(col("filter_interco") == "Y", "intercompany_supplier")
        .when(
            (col("stg_business_entity_id").isNotNull()) &
            (col("client_ecid").isNotNull()),
            "Supplier"
        )
        .when(
            (col("stg_business_entity_id").isNotNull()) &
            (col("stg_business_entity_id") == "2d35a04a-5fdf-50d5-7750-c1c7621ddc33"),
            "Firm"
        )
        .otherwise("")
    )

    # Add `related_business_entity_role` column based on conditions
    transformed_df = transformed_df.withColumn(
        "related_business_entity_role",
        when(col("filter_interco") == "Y", "intercompany_buyer")
        .when(
            (col("stg_payor_business_entity_id").isNotNull()) &
            (col("client_ecid").isNotNull()),
            "Client"
        )
        .when(
            (col("stg_payor_business_entity_id").isNotNull()) &
            (col("stg_payor_business_entity_id") == "2d35a04a-5fdf-50d5-7750-c1c7621ddc33"),
            "Firm"
        )
        .otherwise("")
    )

    #Get vendor contact names from transformed_df
    vendor_names_df = transformed_df.select(
        col("stg_business_entity_id"),
        col("vendor_contact_name").alias("contact_name")
    ).distinct()

    #Joining this with transformed_contacts to get the accurate business_entity_contact_id
    preferred_contacts = vendor_names_df.join(
        transformed_contacts.select("stg_business_entity_id", "contact_name", "business_entity_contact_id"),
        on=["stg_business_entity_id", "contact_name"],
        how="inner"
    ).distinct()

    # Perform a left join between `transformed_business_entity` and `transformed_contacts`
    merged_df = transformed_business_entity.join(
        preferred_contacts,
        on="stg_business_entity_id",
        how="left"
    )

    # Perform an inner join between the result and `transformed_df`
    merged_df = merged_df.join(
        transformed_df,
        on="stg_business_entity_id",
        how="inner"
    )

    # Select required columns
    merged_df = merged_df.select(
        "stg_business_entity_id",
        "business_entity_contact_id",
        "stg_payor_business_entity_id",
        lit(None).alias("related_business_entity_contact_id"),
        "business_entity_role",
        "related_business_entity_role",
        "vendor_id",
        "site_id",
        "client_ecid"
    )

    # Perform another join between `transformed_business_entity` and `transformed_df`
    merged_df1 = transformed_business_entity.join(
        transformed_df,
        transformed_business_entity["stg_business_entity_id"] == transformed_df["stg_jpmc_business_entity_id"],
        how="inner"
    )

    # Select required columns and add missing columns to match `merged_df`
    merged_df1 = merged_df1.select(
        col("stg_jpmc_business_entity_id").alias("stg_business_entity_id"),
        lit(None).alias("business_entity_contact_id"),  # Add missing columns with default values
        col("stg_payor_business_entity_id"),
        lit(None).alias("related_business_entity_contact_id"),
        lit("Firm").alias("business_entity_role"),
        lit("Client").alias("related_business_entity_role"),
        lit(None).alias("vendor_id"),
        lit(None).alias("site_id"),
        lit(None).alias("client_ecid")
    )

    # Union the two DataFrames
    union_df = merged_df.union(merged_df1)

    # Drop duplicates
    union_df = union_df.dropDuplicates()

    # Rename column
    union_df = union_df.withColumnRenamed("stg_payor_business_entity_id", "related_business_entity_id")

    return union_df
    
    

# Call the `relationship` function and assign the result to `transformed_relationship`
transformed_relationship = relationship(transformed_business_entity, transformed_contacts, transformed_df)

transformed_relationship = transformed_relationship.withColumn(
    "business_entity_relationship_id",
    compute_uuid_udf(concat_ws(",", *[col for col in transformed_relationship.columns]))
)



# Show distinct rows in the resulting DataFrame
transformed_relationship.distinct().show(truncate=False)


# Select and rename columns from `transformed_relationship`
transformed_rel_identifiers = transformed_relationship.select(
    col("stg_business_entity_id"),
    col("business_entity_relationship_id"),
    col("vendor_id"),
    col("site_id"),
    col("client_ecid")
)

# List of columns to melt for `transformed_rel_identifiers`
transformed_rel_identifiers_columns = ["vendor_id", "site_id", "client_ecid"]

# Melt `transformed_rel_identifiers` using the `melt_dataframe` function
transformed_rel_identifiers = utl.melt_dataframe(
    transformed_rel_identifiers,
    id_column="business_entity_relationship_id",
    columns_to_melt=transformed_rel_identifiers_columns,
    melted_column_names=("identifier_type", "identifier_value")
)


# Perform a left join between `transformed_identifiers` and `transformed_rel_identifiers`
transformed_rel_identifiers = transformed_rel_identifiers.join(
    transformed_relationship,
    on="business_entity_relationship_id",  # Use the common column for the join
    how="inner"
)

transformed_rel_identifiers = transformed_rel_identifiers.select(
    col("identifier_type"),
    col("identifier_value"),
    col("business_entity_relationship_id").alias("related_identifier")).withColumn("related_identifier_source", lit("relationship"))
    
#transformed_rel_identifiers.show(truncate=False)

relationship_pairs = transformed_rel_identifiers.select(
    "identifier_value", "related_identifier"
).distinct()

# Select columns from `transformed_df` for `transformed_identifiers`
transformed_identifiers = transformed_df.select(*ss.identifiers)

# Melt `transformed_identifiers` using the `melt_dataframe` function
transformed_identifiers = utl.melt_dataframe(
    transformed_identifiers,
    id_column="stg_business_entity_id",
    columns_to_melt=ss.transformed_identifiers_columns,
    melted_column_names=("identifier_type", "identifier_value")
)

#Apply anti-join BEFORE assigning source
melted_business_identifiers  = transformed_identifiers.alias("biz").join(
    broadcast(relationship_pairs).alias("rel"),
    on=[
        col("biz.identifier_value") == col("rel.identifier_value"),
        col("biz.stg_business_entity_id") == col("rel.related_identifier")
    ],
    how="left_anti"
)

# Add `related_identifier` and `related_identifier_source` columns to `transformed_identifiers`
transformed_identifiers = melted_business_identifiers.select(
    col("identifier_type"),
    col("identifier_value"),
    col("stg_business_entity_id").alias("related_identifier")).withColumn("related_identifier_source", lit("business_entity"))




#transformed_identifiers.show(truncate=False)


# # Perform a left join between `transformed_identifiers` and `transformed_rel_identifiers`
# transformed_identifiers = transformed_identifiers.join(
#     transformed_rel_identifiers,
#     on="stg_business_entity_id",  # Use the common column for the join
#     how="left"
# # 

transformed_identifiers = transformed_identifiers.union(transformed_rel_identifiers)

# Drop duplicates
transformed_identifiers = transformed_identifiers.dropDuplicates()

transformed_identifiers = transformed_identifiers.filter(
    col("identifier_value").isNotNull()
)
  
transformed_identifiers = transformed_identifiers.withColumn(
    "identifier_id",
    compute_uuid_udf(concat_ws(",", *[col for col in transformed_identifiers.columns]))
)


# Show the resulting DataFrame
transformed_identifiers.show(truncate=False)

transformed_relationship = transformed_relationship.select(col("business_entity_relationship_id"),col("stg_business_entity_id"),col("business_entity_contact_id"),col("related_business_entity_id"),col("related_business_entity_contact_id"),col("business_entity_role"),col("related_business_entity_role")).distinct()



    
transformed_business_entity = transformed_business_entity.selectExpr(*ss.business_entity_schema).distinct()
transformed_association = transformed_association.selectExpr(*ss.association_schema).distinct()
transformed_revenue = transformed_revenue.selectExpr(*ss.revenue_schema).distinct()
transformed_transaction_stability = transformed_transaction_stability.selectExpr(*ss.transaction_stability_schema).distinct()
transformed_melt_characteristics = transformed_melt_characteristics.selectExpr(*ss.characteristics_schema).distinct()
transformed_contacts = transformed_contacts.selectExpr(*ss.contacts_schema).distinct()
transformed_business_entity_details = transformed_business_entity_details.selectExpr(*ss.business_entity_details_schema).distinct()
transformed_identifiers = transformed_identifiers.selectExpr(*ss.identifiers_schema).distinct()
transformed_melt_industry_classification = transformed_melt_industry_classification.selectExpr(*ss.industry_classification_schema).distinct()
transformed_relationship = transformed_relationship.selectExpr(*ss.relationship_schema).distinct()
transformed_melt_payment_profile_attribute = transformed_melt_payment_profile_attribute.selectExpr(*ss.payment_profile_attribute_schema).distinct()
transformed_spend_analysis = transformed_spend_analysis.selectExpr(*ss.spend_analysis_schema).distinct()
transformed_melt_electronic_address = transformed_melt_electronic_address.selectExpr(*ss.electronic_address_schema).distinct()
transformed_physical_address = transformed_physical_address.selectExpr(*ss.physical_address_schema).distinct()
transformed_melt_restrictions = transformed_melt_restrictions.selectExpr(*ss.restrictions_schema).distinct()
transformed_melt_telecommunication_address = transformed_melt_telecommunication_address.selectExpr(*ss.telecommunication_address_schema).distinct()




# List of DataFrames and their corresponding table names
dataframes_with_tables = {
    "business_entity": transformed_business_entity,
    "business_entity_details": transformed_business_entity_details,
    "business_entity_characteristics": transformed_melt_characteristics,
    "physical_address": transformed_physical_address,
    "business_entity_identifiers": transformed_identifiers,
    "telecommunication_address": transformed_melt_telecommunication_address,
    "electronic_address": transformed_melt_electronic_address,
    "business_entity_spend_analysis": transformed_spend_analysis,
    "restrictions": transformed_melt_restrictions,
    "business_entity_industry_classification": transformed_melt_industry_classification,
    "business_entity_card_association": transformed_association,
    "business_entity_contacts": transformed_contacts,
    "business_entity_relationships": transformed_relationship,
    "business_entity_card_transactions_stability": transformed_transaction_stability,
    "business_entity_card_revenues": transformed_revenue,
    "business_entity_receivables_attribute": transformed_melt_payment_profile_attribute,
}


load_data = utl.load_dataframes_to_postgres(dataframes_with_tables, glueContext, ss, rds_token)







job.commit()

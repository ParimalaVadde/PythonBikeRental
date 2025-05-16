import sys
import boto3
import json
import hashlib
import uuid
import psycopg2
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





region = "us-east-1"
rds_host = "rdsapg86a8-auroratdb-v1-node-1.chzdhpfung6p.us-east-1.rds.amazonaws.com"
rds_port = 6160
db_name = "xbsddevdb"
db_user = "xbsddevdbAuroraAppAdmin"
s3_bucket="s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto"
mapping_file_path="s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto/pfd/mapping/pfd_mapping.csv"
output_data_path="s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto/pfd/temp/transformed_df.csv"
processed_data_path="s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto/pfd/temp/processed_df.csv"
card_data_path ="s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto/pfd/temp/card_revenue.csv"
source_table = "sds_landing.analysis_pfd"
target_table = "sds_landing.analysis_pfd_hist"
schema_dev = "sds_staging"
ssl_cert_s3_path = "s3://app-id-111597-dep-id-114116-uu-id-9x0jt94siuto/cert/us-east-1-bundle.pem"



jsoncol = ["stg_business_entity_id", "registered_agents", "associated_people", "industries", "company_structure", "technologies", "card_revenue", "card_transactions_stability", "associated_tax_ids"]
business_entity = ["stg_business_entity_id", "stg_payor_business_entity_id", "stg_jpmc_business_entity_id"]
business_entity_details = ["stg_business_entity_id", "business_entity_name", "reported_annual_revenue", "year_incorporated", "filter_individual"]
characteristics = ["stg_business_entity_id", "scf_industry_sector_dso_25", "scf_industry_sector_dso_50", "scf_industry_sector_dso_75", "scf_industry_group_dso_25", "scf_industry_group_dso_50", "scf_industry_group_dso_75", "Moody", "SP", "credit_revolver_rate", "cost_of_goods_sold", "vc_campaigned_previously", "vc_acceptance_tier_legacy", "vc_acceptance_tier_model", "vc_acceptance_tier_userdefined", "vc_campaign_count", "vc_campaign_accepts"]
identifiers = ["stg_business_entity_id", "Tax_Id", "DBA", "google_places_id", "enigma_id", "enigma_business_id", "vendor_id", "site_id", "client_ecid"]
physical_address = ["stg_business_entity_id", "country", "state_province", "postal_code", "street_line_1", "street_line_2", "city"]
telecommunication_address = ["stg_business_entity_id", "primary_phone_number", "mobile"]
electronic_address = ["stg_business_entity_id", "email", "website"]
spend_analysis = ["stg_business_entity_id", "stg_payor_business_entity_id", "analysis_conducted_dt", "analysis_external_reference_id", "analysis_stage", "count_of_invoices", "payment_terms", "count_of_payments", "sum_of_payments", "period_start_date", "period_end_date", "payment_ccy", "actual_days_payment_outstanding", "payment_mode", "payment_term_days", "payment_terms_discount_ind", "payment_terms_discount_rate", "payment_terms_discount_days"]
payment_profile = ["stg_business_entity_id", "average_vendor_dso", "average_vendor_dpo", "average_vendor_dio", "enrolled_scf_supplier", "enrolled_vc_supplier", "vc_concierge", "virtual_card_vcn", "spend_on_jpmc_vc", "vc_enrollment_duration_years", "vc_buyercount", "vc_interchange_amt", "cms_enrolled", "cms_subacct_enrolled", "businessbank_enrolled", "vcn_payment_accepted", "product_segmentation_applicable", "jpmc_cc_payment_accepted", "jpmc_cc_spend", "jpmc_cc_enrolled_years", "jpmc_cc_buyer_count", "has_online_payments"]
restrictions = ["stg_business_entity_id", "Do_Not_Campaign"]
industry_classification = ["stg_business_entity_id", "Level-1", "Level-2", "Level-3", "Trust", "Real_Estate", "Govt", "Utilities", "Insurance", "Fi"]
association = ["stg_business_entity_id", "match_confidence", "matched_level_2", "matched_level_3_summary", "matched_level_3_lineitem", "matched_fleet_ind", "matched_data_quality", "matched_mcc", "ind_card_match"]
contacts = ["stg_business_entity_id", "associated_people__name", "associated_people__title"]
revenue = ["stg_business_entity_id", "card_revenue__end_date", "card_revenue__1m__start_date", "card_revenue__1m__average_monthly_amount", "card_revenue__3m__start_date", "card_revenue__3m__average_monthly_amount", "card_revenue__12m__start_date", "card_revenue__12m__average_monthly_amount"]
transaction_stability = ["stg_business_entity_id", "card_transactions_stability__end_date", "card_transactions_stability__1m__start_date", "card_transactions_stability__1m__days_present", "card_transactions_stability__1m__weeks_present", "card_transactions_stability__1m__months_present", "card_transactions_stability__1m__daily_coverage_ratio", "card_transactions_stability__1m__weekly_coverage_ratio", "card_transactions_stability__1m__monthly_coverage_ratio", "card_transactions_stability__3m__start_date", "card_transactions_stability__3m__days_present", "card_transactions_stability__3m__weeks_present", "card_transactions_stability__3m__months_present", "card_transactions_stability__3m__daily_coverage_ratio", "card_transactions_stability__3m__weekly_coverage_ratio", "card_transactions_stability__3m__monthly_coverage_ratio", "card_transactions_stability__12m__start_date", "card_transactions_stability__12m__days_present", "card_transactions_stability__12m__weeks_present", "card_transactions_stability__12m__months_present", "card_transactions_stability__12m__daily_coverage_ratio", "card_transactions_stability__12m__weekly_coverage_ratio", "card_transactions_stability__12m__monthly_coverage_ratio"]



associated_people_schema =  ArrayType(StructType([
                StructField("name", StringType(), True),
                StructField("titles", ArrayType(StringType()), True)
            ]))
            
industries_schema =  ArrayType(StructType([
                StructField("classification_type", StringType(), True),
                StructField("classification_code", StringType(), True),
                StructField("classification_description", StringType(), True)
            ]))
            
company_structure_schema = ArrayType(StructType([
                StructField("corporate_structure", StringType(), True)
            ]))
            
technologies_schema =  ArrayType(StructType([
                StructField("vendor_name", StringType(), True),
                StructField("category", StringType(), True)
            ]))
            
# Define the schema for the `card_revenue` column
card_revenue_schema = ArrayType(StructType([
    StructField("end_date", StringType(), True),
    StructField("1m", StructType([
        StructField("start_date", StringType(), True),
        StructField("average_monthly_amount", DoubleType(), True)
    ])),
    StructField("3m", StructType([
        StructField("start_date", StringType(), True),
        StructField("average_monthly_amount", DoubleType(), True)
    ])),
    StructField("12m", StructType([
        StructField("start_date", StringType(), True),
        StructField("average_monthly_amount", DoubleType(), True)
    ]))
]))



card_transactions_stability =  ArrayType(StructType([
                StructField("end_date", StringType(), True),
                StructField("date_accessible", StringType(), True),
                StructField("1m", StructType([
                    StructField("start_date", StringType(), True),
                    StructField("days_present", IntegerType(), True),
                    StructField("weeks_present", IntegerType(), True),
                    StructField("months_present", IntegerType(), True),
                    StructField("daily_coverage_ratio", DoubleType(), True),
                    StructField("weekly_coverage_ratio", DoubleType(), True),
                    StructField("monthly_coverage_ratio", DoubleType(), True)
                ])),
                StructField("3m", StructType([
                    StructField("start_date", StringType(), True),
                    StructField("days_present", IntegerType(), True),
                    StructField("weeks_present", IntegerType(), True),
                    StructField("months_present", IntegerType(), True),
                    StructField("daily_coverage_ratio", DoubleType(), True),
                    StructField("weekly_coverage_ratio", DoubleType(), True),
                    StructField("monthly_coverage_ratio", DoubleType(), True)
                ])),
                StructField("12m", StructType([
                    StructField("start_date", StringType(), True),
                    StructField("days_present", IntegerType(), True),
                    StructField("weeks_present", IntegerType(), True),
                    StructField("months_present", IntegerType(), True),
                    StructField("daily_coverage_ratio", DoubleType(), True),
                    StructField("weekly_coverage_ratio", DoubleType(), True),
                    StructField("monthly_coverage_ratio", DoubleType(), True)
                ]))
            ]))
            
associated_tax_ids_schema = ArrayType(StringType())
registered_agents_schema = ArrayType(StringType())


# List of columns to melt

payment_profile_columns = [
    "average_vendor_dso", "average_vendor_dpo", "average_vendor_dio", "enrolled_scf_supplier",
    "enrolled_vc_supplier", "vc_concierge", "virtual_card_vcn", "spend_on_jpmc_vc",
    "vc_enrollment_duration_years", "vc_buyercount", "vc_interchange_amt", "cms_enrolled",
    "cms_subacct_enrolled", "businessbank_enrolled", "vcn_payment_accepted",
    "product_segmentation_applicable", "jpmc_cc_payment_accepted", "jpmc_cc_spend",
    "jpmc_cc_enrolled_years", "jpmc_cc_buyer_count", "has_online_payments"
]

telecommunication_address_columns = [ "primary_phone_number", "mobile"]

electronic_address_columns = ["email", "website"]

restrictions_columns = ["Do_Not_Campaign"]


industry_classification_columns = ["Level-1", "Level-2", "Level-3", "Trust", "Real_Estate", "Govt", "Utilities", "Insurance", "Fi"]

transformed_identifiers_columns = [
    "Tax_Id", "DBA", "google_places_id", "enigma_id", "enigma_business_id", "vendor_id", "site_id", "client_ecid"
]

characteristics_columns= [
    "registered_agents", "scf_industry_sector_dso_25", "scf_industry_sector_dso_50",
    "scf_industry_sector_dso_75", "scf_industry_group_dso_25", "scf_industry_group_dso_50",
    "scf_industry_group_dso_75", "Moody", "SP", "credit_revolver_rate", "cost_of_goods_sold",
    "vc_campaigned_previously", "vc_acceptance_tier_legacy", "vc_acceptance_tier_model",
    "vc_acceptance_tier_userdefined", "vc_campaign_count", "vc_campaign_accepts"
]


business_entity_schema =  [
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",  # Cast to STRING
  #  "CAST(source_system_id AS STRING) AS source_system_id",              # Cast to STRING
  #  "CAST(source_system_name AS STRING) AS source_system_name",          # Cast to STRING
  #  "CAST(hierarchy_identifier AS STRING) AS hierarchy_identifier",      # Cast to STRING
  #  "CAST(hierarchy_level AS STRING) AS hierarchy_level",                # Cast to STRING
  #  "CAST(hierarchy_role AS STRING) AS hierarchy_role",                  # Cast to STRING
  #  "CAST(parent_id AS STRING) AS parent_id",                            # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                               # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"             # Add current timestamp for created_date
    ]

association_schema = [
    "CAST(card_association_id AS STRING) AS card_association_id",          # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",    # Cast to STRING
    "CAST(association_name AS STRING) AS association_name",                # Cast to STRING
    "CAST(match_confidence AS STRING) AS match_confidence",                # Cast to STRING
    "CAST(matched_level_2 AS BOOLEAN) AS matched_level_2",                 # Cast to BOOLEAN
    "CAST(matched_level_3_summary AS BOOLEAN) AS matched_level_3_summary", # Cast to BOOLEAN
    "CAST(matched_level_3_lineitem AS BOOLEAN) AS matched_level_3_lineitem", # Cast to BOOLEAN
    "CAST(matched_fleet_ind AS STRING) AS matched_fleet_ind",              # Cast to STRING
    "CAST(matched_mcc AS STRING) AS matched_mcc",                          # Cast to STRING
    "CAST(matched_data_quality AS STRING) AS matched_data_quality",        # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                 # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"               # Add current timestamp for created_date
    ]


revenue_schema = [
    "CAST(revenue_id AS STRING) AS revenue_id",                                  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",          # Cast to STRING
    "CAST(end_date AS DATE) AS end_date",                                        # Cast to DATE
    "CAST(card_revenue__1m__start_date AS DATE) AS card_revenue__1m__start_date", # Cast to DATE
    "CAST(card_revenue__1m__average_monthly_amount AS NUMERIC) AS card_revenue__1m__average_monthly_amount", # Cast to NUMERIC
    "CAST(card_revenue__3m__start_date AS DATE) AS card_revenue__3m__start_date", # Cast to DATE
    "CAST(card_revenue__3m__average_monthly_amount AS NUMERIC) AS card_revenue__3m__average_monthly_amount", # Cast to NUMERIC
    "CAST(card_revenue__12m__start_date AS DATE) AS card_revenue__12m__start_date", # Cast to DATE
    "CAST(card_revenue__12m__average_monthly_amount AS NUMERIC) AS card_revenue__12m__average_monthly_amount", # Cast to NUMERIC
    "CAST('PFD' AS STRING) AS created_by",                                       # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                     # Add current timestamp for created_date
    ]
    
transaction_stability_schema = [
    "CAST(card_transactions_stability_id AS STRING) AS card_transactions_stability_id",  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",                  # Cast to STRING
    "CAST(end_date AS TIMESTAMP) AS end_date",                                           # Cast to TIMESTAMP
   # "CAST(date_accessible AS DATE) AS date_accessible",                                  # Cast to DATE
    "CAST(card_transactions_stability__1m__start_date AS DATE) AS card_transactions_stability__1m__start_date",  # Cast to DATE
    "CAST(card_transactions_stability__1m__days_present AS STRING) AS card_transactions_stability__1m__days_present",  # Cast to STRING
    "CAST(card_transactions_stability__1m__weeks_present AS STRING) AS card_transactions_stability__1m__weeks_present",  # Cast to STRING
    "CAST(card_transactions_stability__1m__months_present AS STRING) AS card_transactions_stability__1m__months_present",  # Cast to STRING
    "CAST(card_transactions_stability__1m__daily_coverage_ratio AS NUMERIC) AS card_transactions_stability__1m__daily_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__1m__weekly_coverage_ratio AS NUMERIC) AS card_transactions_stability__1m__weekly_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__1m__monthly_coverage_ratio AS NUMERIC) AS card_transactions_stability__1m__monthly_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__3m__start_date AS DATE) AS card_transactions_stability__3m__start_date",  # Cast to DATE
    "CAST(card_transactions_stability__3m__days_present AS STRING) AS card_transactions_stability__3m__days_present",  # Cast to STRING
    "CAST(card_transactions_stability__3m__weeks_present AS STRING) AS card_transactions_stability__3m__weeks_present",  # Cast to STRING
    "CAST(card_transactions_stability__3m__months_present AS STRING) AS card_transactions_stability__3m__months_present",  # Cast to STRING
    "CAST(card_transactions_stability__3m__daily_coverage_ratio AS NUMERIC) AS card_transactions_stability__3m__daily_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__3m__weekly_coverage_ratio AS NUMERIC) AS card_transactions_stability__3m__weekly_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__3m__monthly_coverage_ratio AS NUMERIC) AS card_transactions_stability__3m__monthly_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__12m__start_date AS DATE) AS card_transactions_stability__12m__start_date",  # Cast to DATE
    "CAST(card_transactions_stability__12m__days_present AS STRING) AS card_transactions_stability__12m__days_present",  # Cast to STRING
    "CAST(card_transactions_stability__12m__weeks_present AS STRING) AS card_transactions_stability__12m__weeks_present",  # Cast to STRING
    "CAST(card_transactions_stability__12m__months_present AS STRING) AS card_transactions_stability__12m__months_present",  # Cast to STRING
    "CAST(card_transactions_stability__12m__daily_coverage_ratio AS NUMERIC) AS card_transactions_stability__12m__daily_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__12m__weekly_coverage_ratio AS NUMERIC) AS card_transactions_stability__12m__weekly_coverage_ratio",  # Cast to NUMERIC
    "CAST(card_transactions_stability__12m__monthly_coverage_ratio AS NUMERIC) AS card_transactions_stability__12m__monthly_coverage_ratio",  # Cast to NUMERIC
    "CAST('PFD' AS STRING) AS created_by",                                              # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                            # Add current timestamp for created_date
    ] 
    
characteristics_schema = [
    "CAST(characteristics_id AS STRING) AS characteristics_id",          # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",  # Cast to STRING
    "CAST(characteristic_type AS STRING) AS characteristic_type",        # Cast to STRING
    "CAST(characteristic_value AS STRING) AS characteristic_value",      # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                               # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"             # Add current timestamp for created_date
    ]
    
contacts_schema = [
    "CAST(business_entity_contact_id AS STRING) AS business_entity_contact_id",  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",          # Cast to STRING
  #  "CAST(source_system_contact_id AS STRING) AS source_system_contact_id",      # Cast to STRING
  #  "CAST(source_system_name AS STRING) AS source_system_name",                  # Cast to STRING
  #  "CAST(contact_type AS STRING) AS contact_type",                              # Cast to STRING
    "CAST(contact_name AS STRING) AS contact_name",                              # Cast to STRING
    "CAST(contact_title AS STRING) AS contact_title",                            # Cast to STRING
  #  "CAST(contact_active_indicator AS BOOLEAN) AS contact_active_indicator",     # Cast to BOOLEAN
  #  "CAST(contact_deactivated_date AS TIMESTAMP) AS contact_deactivated_date",   # Cast to TIMESTAMP
  #  "CAST(decision_maker_indicator AS STRING) AS decision_maker_indicator",      # Cast to STRING
  #  "CAST(decision_maker_type AS STRING) AS decision_maker_type",                # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                       # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                     # Add current timestamp for created_date
    ]
    
business_entity_details_schema = [
    "CAST(business_entity_details_id AS STRING) AS business_entity_details_id",  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",          # Cast to STRING
    "CAST(business_entity_name AS STRING) AS business_entity_name",              # Cast to STRING
    "CAST(company_structure AS STRING) AS company_structure",                    # Cast to STRING
   # "CAST(market_segment_type AS STRING) AS market_segment_type",                # Cast to STRING
    "CAST(year_incorporated AS STRING) AS year_incorporated",                    # Cast to STRING
    "CAST(reported_annual_revenue AS STRING) AS reported_annual_revenue",        # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                       # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                     # Add current timestamp for created_date
    ]
    
identifiers_schema = [
    "CAST(identifier_id AS STRING) AS identifier_id",                          # Cast to STRING
    "CAST(identifier_type AS STRING) AS identifier_type",                      # Cast to STRING
    "CAST(identifier_value AS STRING) AS identifier_value",                    # Cast to STRING
    "CAST(related_identifier AS STRING) AS related_identifier",                # Cast to STRING
    "CAST(related_identifier_source AS STRING) AS related_identifier_source",  # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                     # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                   # Add current timestamp for created_date
    ]
    
industry_classification_schema = [
    "CAST(classification_id AS STRING) AS classification_id",                  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",        # Cast to STRING
    "CAST(classification_type AS STRING) AS classification_type",              # Cast to STRING
    "CAST(classification_code AS STRING) AS classification_code",              # Cast to STRING
    "CAST(classification_description AS STRING) AS classification_description",# Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                     # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                   # Add current timestamp for created_date
    ]
    
relationship_schema = [
    "CAST(business_entity_relationship_id AS STRING) AS business_entity_relationship_id",  # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",                    # Cast to STRING
    "CAST(business_entity_contact_id AS STRING) AS business_entity_contact_id",            # Cast to STRING
    "CAST(related_business_entity_id AS STRING) AS stg_related_business_entity_id",        # Cast to STRING
    "CAST(related_business_entity_contact_id AS STRING ) AS related_business_entity_contact_id",    #cast to STRING
    "CAST(business_entity_role AS STRING) AS business_entity_role",                        # Cast to STRING
    "CAST(related_business_entity_role AS STRING) AS related_business_entity_role",        # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                                 # Add constant value for created_by
    "CAST(current_date() AS DATE) AS created_date"                                         # Add current date for created_date
    ]
    
payment_profile_attribute_schema = [
    "CAST(attribute_id AS STRING) AS attribute_id",                              # Cast to STRING
    "CAST(stg_business_entity_id AS STRING) AS stg_business_entity_id",                  # Cast to STRING
    "CAST(receivables_attribute_type AS STRING) AS receivables_attribute_type",  # Cast to STRING
    "CAST(receivables_attribute_value AS STRING) AS receivables_attribute_value",# Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                       # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                     # Add current timestamp for created_date
    ]
    
spend_analysis_schema = [
    "CAST(spend_analysis_id AS STRING) AS spend_analysis_id",                          # Cast to STRING
    "CAST(stg_payor_business_entity_id AS STRING) AS stg_payor_business_entity_id",    # Cast to STRING
    "CAST(stg_payee_business_entity_id AS STRING) AS stg_payee_business_entity_id",    # Cast to STRING
    "CAST(analysis_conducted_dt AS STRING) AS analysis_conducted_dt",                  # Cast to STRING
    "CAST(analysis_external_reference_id AS STRING) AS analysis_external_reference_id",# Cast to STRING
    "CAST(analysis_stage AS STRING) AS analysis_stage",                                # Cast to STRING
    "CAST(count_of_invoices AS NUMERIC) AS count_of_invoices",                         # Cast to NUMERIC
    "CAST(payment_terms AS STRING) AS payment_terms",                                  # Cast to STRING
    "CAST(count_of_payments AS NUMERIC) AS count_of_payments",                         # Cast to NUMERIC
    "CAST(sum_of_payments AS NUMERIC) AS sum_of_payments",                             # Cast to NUMERIC
    "CAST(period_start_date AS DATE) AS period_start_date",                            # Cast to DATE
    "CAST(period_end_date AS DATE) AS period_end_date",                                # Cast to DATE
    "CAST(payment_ccy AS STRING) AS payment_ccy",                                      # Cast to STRING
   # "CAST(chargeback_amount AS NUMERIC) AS chargeback_amount",                         # Cast to NUMERIC
    #"CAST(chargeback_percentage AS NUMERIC) AS chargeback_percentage",                 # Cast to NUMERIC
    "CAST(actual_days_payment_outstanding AS NUMERIC) AS actual_days_payment_outstanding", # Cast to NUMERIC
    "CAST(payment_mode AS STRING) AS payment_mode",                                    # Cast to STRING
    "CAST(payment_term_days AS NUMERIC) AS payment_term_days",                         # Cast to NUMERIC
    "CAST(payment_terms_discount_ind AS STRING) AS payment_terms_discount_ind",        # Cast to STRING
    "CAST(payment_terms_discount_rate AS NUMERIC) AS payment_terms_discount_rate",     # Cast to NUMERIC
    "CAST(payment_terms_discount_days AS NUMERIC) AS payment_terms_discount_days",     # Cast to NUMERIC
    #"CAST(source_system_id AS STRING) AS source_system_id",                            # Cast to STRING
    #"CAST(source_system_name AS STRING) AS source_system_name",                        # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                             # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                           # Add current timestamp for created_date
    ]
    
electronic_address_schema = [
    "CAST(electronic_address_id AS STRING) AS electronic_address_id",              # Cast to STRING
    "CAST(related_identifier AS STRING) AS related_identifier",                    # Cast to STRING
    "CAST(related_identifier_source AS STRING) AS related_identifier_source",      # Cast to STRING
    "CAST(electronic_address_type AS STRING) AS electronic_address_type",          # Cast to STRING
    "CAST(electronic_address AS STRING) AS electronic_address",                    # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                         # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                       # Add current timestamp for created_date
    ]
    
physical_address_schema = [
    "CAST(physical_address_id AS STRING) AS physical_address_id",              # Cast to STRING
    "CAST(related_identifier AS STRING) AS related_identifier",                # Cast to STRING
    "CAST(related_identifier_source AS STRING) AS related_identifier_source",  # Cast to STRING
    "CAST(physical_address_type AS STRING) AS physical_address_type",          # Cast to STRING
    "CAST(street_line_1 AS STRING) AS street_line_1",                          # Cast to STRING
    "CAST(street_line_2 AS STRING) AS street_line_2",                          # Cast to STRING
  #  "CAST(street_line_3 AS STRING) AS street_line_3",                          # Cast to STRING
    "CAST(country AS STRING) AS country",                                      # Cast to STRING
    "CAST(city AS STRING) AS city",                                            # Cast to STRING
    "CAST(state_province AS STRING) AS state_province",                        # Cast to STRING
    "CAST(postal_code AS STRING) AS postal_code",                              # Cast to STRING
  #  "CAST(location_name AS STRING) AS location_name",                          # Cast to STRING
  #  "CAST(site_identifier AS STRING) AS site_identifier",                      # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                     # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                   # Add current timestamp for created_date
    ]
    
restrictions_schema = [
    "CAST(restriction_id AS STRING) AS restriction_id",                          # Cast to STRING
    "CAST(related_identifier AS STRING) AS related_identifier",                  # Cast to STRING
    "CAST(related_identifier_source AS STRING) AS related_identifier_source",    # Cast to STRING
    "CAST(restriction_type AS STRING) AS restriction_type",                      # Cast to STRING
    "CAST(restriction_indicator AS BOOLEAN) AS restriction_indicator",           # Cast to BOOLEAN
#    "CAST(restriction_reason AS STRING) AS restriction_reason",                  # Cast to STRING
 #   "CAST(restriction_for_products AS STRING) AS restriction_for_products",      # Cast to STRING
  #  "CAST(restriction_added_dt AS DATE) AS restriction_added_dt",                # Cast to DATE
    "CAST('PFD' AS STRING) AS created_by",                                       # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                     # Add current timestamp for created_date
    ]
    
telecommunication_address_schema = [
    "CAST(telecommunication_address_id AS STRING) AS telecommunication_address_id",  # Cast to STRING
    "CAST(related_identifier AS STRING) AS related_identifier",                      # Cast to STRING
    "CAST(related_identifier_source AS STRING) AS related_identifier_source",        # Cast to STRING
    "CAST(telecommunication_address_type AS STRING) AS telecommunication_address_type",  # Cast to STRING
   # "CAST(area_dialing_code AS STRING) AS area_dialing_code",                        # Cast to STRING
    "CAST(phone_number AS STRING) AS phone_number",                                  # Cast to STRING
   # "CAST(extension_number AS STRING) AS extension_number",                          # Cast to STRING
    "CAST('PFD' AS STRING) AS created_by",                                           # Add constant value for created_by
    "CAST(current_timestamp() AS TIMESTAMP) AS created_date"                         # Add current timestamp for created_date
    ]

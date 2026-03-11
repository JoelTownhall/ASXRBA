#!/usr/bin/env Rscript

# Daily ASX rate scraper - based on Matt Cowgill's R scraper at
# https://github.com/MattCowgill/cash-rate-scraper.git
# crontab: 01 20 * * 1-5 /Users/bryanpalmer/ASX/ASX-daily-capture.sh

# Load required libraries
library(httr2)
library(jsonlite)
library(dplyr)
library(lubridate)
library(readr)

# Function to request data from URL
request_get <- function(url) {
  # Use httr2 to get the contents of the specified URL
  response <- request(url) |>
    req_timeout(20) |>
    req_perform()

  if (resp_status(response) != 200) {
    stop("HTTP request failed with status: ", resp_status(response))
  }

  return(resp_body_string(response))
}

# Naming conventions
CASH_RATE <- "cash_rate"
SCRAPE_DATE <- "scrape_date"
DATE <- "date"
FILE_STEM <- "scraped_cash_rate_"

# Function to get ASX data
get_asx_data <- function() {
  # Capture the latest ASX rate tracker data from the ASX website
  # and return it as a data frame

  url <- paste0(
    "https://asx.api.markitdigital.com/asx-research/1.0/derivatives/",
    "interest-rate/IB/futures?days=1&height=179&width=179"
  )

  raw_json <- request_get(url)
  json_data <- fromJSON(raw_json)
  df <- as.data.frame(json_data$data$items)

  # Calculate cash rate
  df[[CASH_RATE]] <- round(100 - df$pricePreviousSettlement, 3)

  # Set scrape date
  df[[SCRAPE_DATE]] <- df$dateLastTrade

  # Create date column from dateExpiry (converted to period/yearmon format)
  df[[DATE]] <- format(as.Date(df$dateExpiry), "%Y-%m")

  # Select and reorder columns, with date as the first column
  result <- df |>
    select(all_of(c(DATE, CASH_RATE, SCRAPE_DATE)))

  return(result)
}

# Function to save ASX data
save_asx_data <- function(df) {
  # Save the ASX rate tracker data to a CSV file

  directory <- "./ASX_DAILY_DATA/"

  # Create directory if it doesn't exist
  if (!dir.exists(directory)) {
    dir.create(directory, recursive = TRUE)
  }

  file_date <- format(Sys.Date(), "%Y-%m-%d")
  filename <- paste0(directory, FILE_STEM, file_date, ".csv")

  write_csv(df, filename)

  message("Data saved to: ", filename)
}

# Main function
main <- function() {
  # The main function to capture and save the ASX rate tracker data

  df <- get_asx_data()
  save_asx_data(df)
}

# Run main function
main()

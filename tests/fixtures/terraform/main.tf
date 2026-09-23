terraform {
  required_version = ">= 1.6"
}

provider "aws" {
  region = "eu-west-2"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "example-artifacts"
}

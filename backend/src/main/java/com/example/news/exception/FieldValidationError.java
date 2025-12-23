package com.example.news.exception;

public record FieldValidationError(
        String field,
        String message
) {
}

package com.example.news.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewsEntrySourceRequest(
        @NotBlank @Size(max = 255) String name,
        @NotBlank @Size(max = 1024) String url
) {
}

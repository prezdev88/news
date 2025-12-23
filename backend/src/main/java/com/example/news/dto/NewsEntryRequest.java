package com.example.news.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.List;

public record NewsEntryRequest(
        @jakarta.validation.constraints.NotNull LocalDate date,
        @NotBlank @Size(max = 500) String headline,
        List<@Size(min = 1, max = 100) String> hashtags,
        List<@Valid NewsEntrySourceRequest> sources
) {
}

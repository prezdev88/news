package com.example.news.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public record NewsEntryResponse(
        UUID id,
        LocalDate date,
        String headline,
        List<String> hashtags,
        List<NewsEntrySourceResponse> sources,
        Instant createdAt,
        Instant updatedAt
) {
}

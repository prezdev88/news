package com.example.news.dto;

import java.util.UUID;

public record NewsEntrySourceResponse(
        UUID id,
        String name,
        String url
) {
}

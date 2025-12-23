package com.example.news.dto;

import java.time.Instant;

public record HashtagResponse(
        String tag,
        long entryCount,
        Instant createdAt
) {
}

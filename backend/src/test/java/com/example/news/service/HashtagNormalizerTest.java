package com.example.news.service;

import com.example.news.exception.BadRequestException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HashtagNormalizerTest {

    private final HashtagNormalizer normalizer = new HashtagNormalizer();

    @Test
    void normalizesHashtags() {
        String normalized = normalizer.normalize("  #Ka st  ");
        assertEquals("kast", normalized);
    }

    @Test
    void rejectsInvalidHashtag() {
        assertThrows(BadRequestException.class, () -> normalizer.normalize("#"));
        assertThrows(BadRequestException.class, () -> normalizer.normalize("#!bad"));
    }
}

package com.example.news.service;

import com.example.news.exception.BadRequestException;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

@Component
public class HashtagNormalizer {

    private static final String ALLOWED_PATTERN = "^[a-z0-9_-]{2,50}$";

    public String normalize(String rawTag) {
        if (!StringUtils.hasText(rawTag)) {
            throw new BadRequestException("Hashtag no puede ser vacío");
        }
        String cleaned = rawTag.trim();
        while (cleaned.startsWith("#")) {
            cleaned = cleaned.substring(1);
        }
        cleaned = cleaned.toLowerCase(Locale.ROOT);
        cleaned = cleaned.replaceAll("\\s+", "");

        if (!cleaned.matches(ALLOWED_PATTERN)) {
            throw new BadRequestException("Hashtag inválido: debe tener 2-50 caracteres [a-z0-9_-]");
        }
        return cleaned;
    }

    public Set<String> normalizeMany(Iterable<String> tags) {
        Set<String> normalized = new LinkedHashSet<>();
        if (tags == null) {
            return normalized;
        }
        for (String tag : tags) {
            normalized.add(normalize(tag));
        }
        return normalized;
    }
}

package com.example.news.spec;

import com.example.news.domain.Hashtag;
import com.example.news.domain.NewsEntry;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.util.StringUtils;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class NewsEntrySpecifications {

    private NewsEntrySpecifications() {
    }

    public static Specification<NewsEntry> withFilters(LocalDate from,
                                                        LocalDate to,
                                                        String query,
                                                        Set<String> hashtags) {
        return (root, cq, cb) -> {
            List<jakarta.persistence.criteria.Predicate> predicates = new ArrayList<>();

            if (from != null) {
                predicates.add(cb.greaterThanOrEqualTo(root.get("date"), from));
            }
            if (to != null) {
                predicates.add(cb.lessThanOrEqualTo(root.get("date"), to));
            }
            if (StringUtils.hasText(query)) {
                String like = "%" + query.toLowerCase() + "%";
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("headline")), like)
                ));
            }
            if (hashtags != null && !hashtags.isEmpty()) {
                Join<NewsEntry, Hashtag> hashtagJoin = root.join("hashtags", JoinType.LEFT);
                predicates.add(hashtagJoin.get("tag").in(hashtags));
                cq.distinct(true);
            }

            return cb.and(predicates.toArray(new jakarta.persistence.criteria.Predicate[0]));
        };
    }
}

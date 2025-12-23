package com.example.news.repository;

import com.example.news.domain.Hashtag;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface HashtagRepository extends JpaRepository<Hashtag, UUID> {

    Optional<Hashtag> findByTag(String tag);

    List<Hashtag> findByTagIn(Collection<String> tags);

    List<Hashtag> findByTagStartingWithIgnoreCaseOrderByTagAsc(String prefix);

    List<Hashtag> findAllByOrderByTagAsc();

    @Query("select count(distinct e) from NewsEntry e join e.hashtags h where h.tag = :tag")
    long countEntriesWithTag(String tag);
}

package com.example.news.repository;

import com.example.news.domain.NewsEntry;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface NewsEntryRepository extends JpaRepository<NewsEntry, UUID>, JpaSpecificationExecutor<NewsEntry> {

    @Override
    @EntityGraph(attributePaths = {"hashtags", "sources"})
    List<NewsEntry> findAll(org.springframework.data.jpa.domain.Specification<NewsEntry> spec, org.springframework.data.domain.Sort sort);

    @EntityGraph(attributePaths = {"hashtags", "sources"})
    Optional<NewsEntry> findWithDetailsById(UUID id);

    @EntityGraph(attributePaths = {"hashtags", "sources"})
    Page<NewsEntry> findAll(org.springframework.data.jpa.domain.Specification<NewsEntry> spec, Pageable pageable);
}

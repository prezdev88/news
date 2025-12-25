CREATE TABLE hashtag (
    id UUID PRIMARY KEY,
    tag VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE news_entry (
    id UUID PRIMARY KEY,
    date DATE NOT NULL,
    headline VARCHAR(500) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE news_entry_hashtag (
    entry_id UUID NOT NULL REFERENCES news_entry(id) ON DELETE CASCADE,
    hashtag_id UUID NOT NULL REFERENCES hashtag(id) ON DELETE CASCADE,
    CONSTRAINT uk_entry_hashtag UNIQUE (entry_id, hashtag_id)
);

CREATE TABLE news_entry_source (
    id UUID PRIMARY KEY,
    entry_id UUID NOT NULL REFERENCES news_entry(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_entry_date ON news_entry(date);
CREATE UNIQUE INDEX idx_hashtag_tag ON hashtag(tag);
CREATE INDEX idx_entry_hashtag_hashtag_id ON news_entry_hashtag(hashtag_id);
CREATE INDEX idx_source_entry_id ON news_entry_source(entry_id);

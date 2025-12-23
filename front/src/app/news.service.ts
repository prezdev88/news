import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export interface NewsEntryResponse {
  id: string;
  date: string;
  headline: string;
  hashtags: string[];
  sources: { id: string; name: string; url: string }[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateEntryRequest {
  date: string;
  headline: string;
  hashtags?: string[];
  sources?: { name: string; url: string }[];
}

export interface HashtagResponse {
  tag: string;
  entryCount: number;
  createdAt: string;
}

@Injectable({ providedIn: 'root' })
export class NewsService {
  private base = environment.apiBase;

  constructor(private http: HttpClient) {}

  listEntries(filters: { from?: string; to?: string; q?: string; hashtags?: string[] }): Observable<NewsEntryResponse[]> {
    let params = new HttpParams();
    if (filters.from) params = params.set('from', filters.from);
    if (filters.to) params = params.set('to', filters.to);
    if (filters.q) params = params.set('q', filters.q);
    if (filters.hashtags && filters.hashtags.length) {
      params = params.set('hashtags', filters.hashtags.join(','));
    }
    return this.http.get<NewsEntryResponse[]>(`${this.base}/entries`, { params });
  }

  createEntry(payload: CreateEntryRequest): Observable<NewsEntryResponse> {
    return this.http.post<NewsEntryResponse>(`${this.base}/entries`, payload);
  }

  listHashtags(q?: string): Observable<HashtagResponse[]> {
    const params = q ? new HttpParams().set('q', q) : undefined;
    return this.http.get<HashtagResponse[]>(`${this.base}/hashtags`, { params });
  }
}

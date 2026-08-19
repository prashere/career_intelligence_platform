import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button } from '../ui/Primitives';

export type Bucket = 'matches' | 'closing_soon' | 'saved' | 'applied' | 'dismissed';
export type SortMode = 'fit' | 'deadline';

export interface FeedFilterState {
  bucket: Bucket;
  sort: SortMode;
  search: string;
  opportunity_type: string;
  funding_type: string;
  verified_only: boolean;
}

const BUCKETS: { key: Bucket; label: string }[] = [
  { key: 'matches', label: 'Matches' },
  { key: 'closing_soon', label: 'Closing soon' },
  { key: 'saved', label: 'Saved' },
  { key: 'applied', label: 'Applied' },
  { key: 'dismissed', label: 'Dismissed' },
];

export function readFiltersFromParams(params: URLSearchParams): FeedFilterState {
  const bucket = params.get('bucket') as Bucket | null;
  const sort = params.get('sort') as SortMode | null;
  return {
    bucket: bucket && BUCKETS.some((b) => b.key === bucket) ? bucket : 'matches',
    sort: sort === 'deadline' ? 'deadline' : 'fit',
    search: params.get('search') || '',
    opportunity_type: params.get('type') || '',
    funding_type: params.get('funding') || '',
    verified_only: params.get('verified') === '1',
  };
}

export function writeFiltersToParams(filters: FeedFilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (filters.bucket !== 'matches') p.set('bucket', filters.bucket);
  if (filters.sort !== 'fit') p.set('sort', filters.sort);
  if (filters.search) p.set('search', filters.search);
  if (filters.opportunity_type) p.set('type', filters.opportunity_type);
  if (filters.funding_type) p.set('funding', filters.funding_type);
  if (filters.verified_only) p.set('verified', '1');
  return p;
}

interface Props {
  onApply: (filters: FeedFilterState) => void;
}

export default function FeedFilters({ onApply }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = readFiltersFromParams(searchParams);
  const [searchInput, setSearchInput] = useState(filters.search);

  useEffect(() => {
    setSearchInput(filters.search);
  }, [filters.search]);

  function update(partial: Partial<FeedFilterState>) {
    const next = { ...filters, ...partial };
    setSearchParams(writeFiltersToParams(next), { replace: true });
    onApply(next);
  }

  return (
    <div className="dashboard-filters">
      <div className="dashboard-bucket-tabs" role="tablist">
        {BUCKETS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filters.bucket === key}
            className={`dashboard-bucket-tab${filters.bucket === key ? ' active' : ''}`}
            onClick={() => update({ bucket: key })}
          >
            {label}
          </button>
        ))}
      </div>

      <form
        className="dashboard-filter-form"
        onSubmit={(e) => {
          e.preventDefault();
          update({ search: searchInput.trim() });
        }}
      >
        <label className="dashboard-filter-field">
          <span className="dashboard-filter-label">Search</span>
          <input
            type="search"
            className="dashboard-filter-input"
            placeholder="Title, field, institution…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </label>
        <label className="dashboard-filter-field">
          <span className="dashboard-filter-label">Type</span>
          <select
            className="dashboard-filter-select"
            value={filters.opportunity_type}
            onChange={(e) => update({ opportunity_type: e.target.value })}
          >
            <option value="">Any</option>
            <option value="scholarship">Scholarship</option>
            <option value="fellowship">Fellowship</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="dashboard-filter-field">
          <span className="dashboard-filter-label">Funding</span>
          <select
            className="dashboard-filter-select"
            value={filters.funding_type}
            onChange={(e) => update({ funding_type: e.target.value })}
          >
            <option value="">Any</option>
            <option value="full">Fully funded</option>
            <option value="partial">Partial</option>
          </select>
        </label>
        <label className="dashboard-filter-field dashboard-filter-check">
          <input
            type="checkbox"
            checked={filters.verified_only}
            onChange={(e) => update({ verified_only: e.target.checked })}
          />
          <span>Verified only</span>
        </label>
        <label className="dashboard-filter-field">
          <span className="dashboard-filter-label">Sort</span>
          <select
            className="dashboard-filter-select"
            value={filters.sort}
            onChange={(e) => update({ sort: e.target.value as SortMode })}
          >
            <option value="fit">Best fit</option>
            <option value="deadline">Deadline</option>
          </select>
        </label>
        <Button type="submit" variant="primary" className="dashboard-filter-submit">
          Search
        </Button>
      </form>
    </div>
  );
}

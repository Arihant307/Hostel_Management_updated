import { useCallback, useEffect, useRef, useState } from 'react';
import useDebounce from './useDebounce.js';
import { getErrorMessage } from '../services/api.js';

/**
 * State for a server-paginated, filterable, sortable list.
 *
 *   const list = usePaginatedList(studentService.list, { initialFilters: { status: '' } });
 *   list.setFilter('status', 'active'); list.setSort({ key, order }); list.reload();
 *
 * `search` is debounced; any filter/sort change resets to page 1. Responses that
 * arrive out of order are ignored.
 */
export default function usePaginatedList(fetcher, { initialFilters = {}, initialSort, perPage = 10 } = {}) {
  const [filters, setFilters] = useState({ search: '', ...initialFilters });
  const [sort, setSortState] = useState(initialSort ?? null);
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ items: [], pagination: null, extra: {}, loading: true, error: '' });
  const debouncedSearch = useDebounce(filters.search);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const { search: _ignored, ...otherFilters } = filters;
  const filterKey = JSON.stringify(otherFilters);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setState((s) => ({ ...s, loading: true, error: '' }));
    try {
      const params = {
        ...JSON.parse(filterKey),
        search: debouncedSearch,
        page,
        per_page: perPage,
        ...(sort ? { sort: sort.key, order: sort.order } : {}),
      };
      const { items, pagination, ...extra } = await fetcherRef.current(params);
      if (id === requestId.current) setState({ items, pagination, extra, loading: false, error: '' });
    } catch (err) {
      if (id === requestId.current) setState((s) => ({ ...s, loading: false, error: getErrorMessage(err) }));
    }
  }, [filterKey, debouncedSearch, page, perPage, sort]);

  useEffect(() => {
    load();
  }, [load]);

  const setFilter = useCallback((key, value) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({ search: '', ...initialFilters });
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setSort = useCallback((value) => {
    setSortState(value);
    setPage(1);
  }, []);

  const { search: _initialSearch, ...initialOthers } = { search: '', ...initialFilters };
  const hasFilters = Boolean(debouncedSearch) || JSON.stringify(otherFilters) !== JSON.stringify(initialOthers);

  return { ...state, filters, setFilter, resetFilters, hasFilters, sort, setSort, page, setPage, reload: load };
}

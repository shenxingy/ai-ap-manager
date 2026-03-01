import { useAuthStore } from '../auth';

describe('auth store', () => {
  beforeEach(() => {
    // Clear the store before each test
    useAuthStore.setState({
      token: null,
      user: null,
      rememberMe: true,
    });
    // Clear storage
    localStorage.clear();
    sessionStorage.clear();
  });

  it('has initial state with no user and token', () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.token).toBeNull();
  });

  it('setAuth stores user and token', () => {
    const user = { id: '1', email: 'test@test.com', name: 'Test User', role: 'AP_CLERK' };
    const token = 'test-token-123';

    useAuthStore.getState().setAuth(token, user);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(user);
    expect(state.token).toEqual(token);
  });

  it('setAuth respects rememberMe flag', () => {
    const user = { id: '1', email: 'test@test.com', name: 'Test User', role: 'AP_CLERK' };
    const token = 'test-token-123';

    useAuthStore.getState().setAuth(token, user, false);

    const state = useAuthStore.getState();
    expect(state.rememberMe).toBe(false);
  });

  it('logout clears user and token', () => {
    const user = { id: '1', email: 'test@test.com', name: 'Test User', role: 'AP_CLERK' };
    const token = 'test-token-123';

    useAuthStore.getState().setAuth(token, user);
    expect(useAuthStore.getState().user).not.toBeNull();

    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.token).toBeNull();
  });

  it('setAuth stores rememberMe state correctly', () => {
    const user = { id: '1', email: 'test@test.com', name: 'Test User', role: 'APPROVER' };
    const token = 'test-token-123';

    useAuthStore.getState().setAuth(token, user, true);
    expect(useAuthStore.getState().rememberMe).toBe(true);

    useAuthStore.getState().setAuth(token, user, false);
    expect(useAuthStore.getState().rememberMe).toBe(false);
  });

  it('setAuth defaults rememberMe to true', () => {
    const user = { id: '1', email: 'test@test.com', name: 'Test User', role: 'AP_CLERK' };
    const token = 'test-token-123';

    useAuthStore.getState().setAuth(token, user);

    const state = useAuthStore.getState();
    expect(state.rememberMe).toBe(true);
  });
});

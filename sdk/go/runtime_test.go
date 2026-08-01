package bentobox

import (
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func TestCheckPermission(t *testing.T) {
	policy := CompartmentConfig{Permissions: []string{"fs_read", "fs_write"}}
	ok, err := CheckPermission(policy, "fs_read")
	if err != nil || !ok {
		t.Fatalf("expected fs_read allowed, got ok=%v err=%v", ok, err)
	}
	ok, err = CheckPermission(policy, "network")
	if err != nil || ok {
		t.Fatalf("expected network denied, got ok=%v err=%v", ok, err)
	}
}

func TestCheckCommand(t *testing.T) {
	for _, blocked := range []string{"rm -rf /", "sudo whoami", "dd if=/dev/zero of=/dev/sda"} {
		ok, _ := CheckCommand(blocked)
		if ok {
			t.Errorf("expected %q to be blocked", blocked)
		}
	}
	ok, err := CheckCommand("grep foo file.txt")
	if err != nil || !ok {
		t.Fatalf("expected simple grep allowed, got ok=%v err=%v", ok, err)
	}
}

func TestSnapshotRestore(t *testing.T) {
	work := filepath.Join(os.TempDir(), "bw_go_snap", "work")
	snap := filepath.Join(os.TempDir(), "bw_go_snap", ".snapshots")
	os.RemoveAll(filepath.Join(os.TempDir(), "bw_go_snap"))
	defer os.RemoveAll(filepath.Join(os.TempDir(), "bw_go_snap"))

	os.MkdirAll(work, 0o755)
	file := filepath.Join(work, "a.txt")
	os.WriteFile(file, []byte("hello"), 0o644)

	n, err := Snapshot(work, snap, nil)
	if err != nil || n != 1 {
		t.Fatalf("snapshot: n=%d err=%v", n, err)
	}

	os.WriteFile(file, []byte("changed"), 0o644)
	restored, err := Restore(work, snap)
	if err != nil || restored != 1 {
		t.Fatalf("restore: n=%d err=%v", restored, err)
	}
	got, _ := os.ReadFile(file)
	if string(got) != "hello" {
		t.Fatalf("expected 'hello' after restore, got %q", got)
	}
}

func TestValidateRuntime(t *testing.T) {
	configs := []CompartmentConfig{
		{Name: "lint", Permissions: []string{"fs_read", "fs_exec"}},
		{Name: "build", Permissions: []string{"fs_read", "fs_write", "fs_exec"}},
	}
	ok, err := ValidateRuntime(configs, [][2]string{{"lint", "build"}})
	if err != nil || !ok {
		t.Fatalf("expected valid runtime, ok=%v err=%v", ok, err)
	}
	ok, err = ValidateRuntime(configs, [][2]string{{"lint", "nope"}})
	if err != nil || ok {
		t.Fatalf("expected invalid runtime, ok=%v err=%v", ok, err)
	}
}

func TestCanRoute(t *testing.T) {
	configs := []CompartmentConfig{
		{Name: "a", AllowOutboundTo: []string{"b"}},
		{Name: "b"},
		{Name: "c", AllowInboundFrom: []string{}},
	}
	ok, err := CanRoute(configs, "a", "b")
	if err != nil || !ok {
		t.Fatalf("expected a->b allowed, got ok=%v err=%v", ok, err)
	}
	ok, err = CanRoute(configs, "b", "a")
	if err != nil || !ok {
		t.Fatalf("expected b->a allowed (wildcard default), got ok=%v err=%v", ok, err)
	}
	ok, err = CanRoute(configs, "a", "c")
	if err != nil || ok {
		t.Fatalf("expected a->c denied, got ok=%v err=%v", ok, err)
	}
	ok, err = CanRoute(configs, "b", "c")
	if err != nil || ok {
		t.Fatalf("expected b->c denied, got ok=%v err=%v", ok, err)
	}
	_, err = CanRoute(configs, "zzz", "b")
	if err == nil {
		t.Fatal("expected error for unknown compartment")
	}
}

func TestCredentialRewriteAndResolve(t *testing.T) {
	routes := []RouteConfig{{
		Prefix:   "/openai",
		Upstream: "https://api.openai.com",
	}}
	url, err := CredentialRewrite(routes, "/openai/v1/chat")
	if err != nil || url != "https://api.openai.com/v1/chat" {
		t.Fatalf("rewrite: url=%q err=%v", url, err)
	}
	url, err = CredentialRewrite(routes, "/anthropic/v1")
	if err != nil || url != "" {
		t.Fatalf("expected no match, url=%q err=%v", url, err)
	}

	os.Setenv("BW_TEST_KEY", "sk-test")
	defer os.Unsetenv("BW_TEST_KEY")
	if got := CredentialResolve("env:BW_TEST_KEY"); got != "sk-test" {
		t.Fatalf("expected sk-test, got %q", got)
	}
	if got := CredentialResolve("env:BW_MISSING_KEY"); got != "" {
		t.Fatalf("expected empty for missing env, got %q", got)
	}
}

func TestCredentialRewriteNoMatchIsEmpty(t *testing.T) {
	routes := []RouteConfig{{Prefix: "/x", Upstream: "https://x.example"}}
	url, err := CredentialRewrite(routes, "/y")
	if err != nil || url != "" {
		t.Fatalf("expected empty URL + nil error for no match, url=%q err=%v", url, err)
	}
}

func TestRuntimeHandle(t *testing.T) {
	configs := []CompartmentConfig{
		{Name: "a", AllowOutboundTo: []string{"b"}},
		{Name: "b"},
		{Name: "c", AllowInboundFrom: []string{}}, // explicit empty, not wildcard
	}
	rt, err := NewRuntime(configs, [][2]string{{"a", "b"}})
	if err != nil {
		t.Fatalf("NewRuntime: %v", err)
	}
	defer rt.Free()

	ok, err := rt.CanRoute("a", "b")
	if err != nil || !ok {
		t.Fatalf("expected a->b allowed, got ok=%v err=%v", ok, err)
	}
	ok, err = rt.CanRoute("b", "a")
	if err != nil || !ok {
		t.Fatalf("expected b->a allowed (wildcard), got ok=%v err=%v", ok, err)
	}
	ok, err = rt.CanRoute("b", "c")
	if err != nil || ok {
		t.Fatalf("expected b->c denied, got ok=%v err=%v", ok, err)
	}
	_, err = rt.CanRoute("zzz", "b")
	if err == nil {
		t.Fatal("expected error for unknown compartment")
	}

	order, err := rt.RunOrder("")
	if err != nil || len(order) != 3 || order[0] != "a" || order[2] != "c" {
		t.Fatalf("run_order: %v err=%v", order, err)
	}
	order, err = rt.RunOrder("b")
	if err != nil || len(order) != 2 || order[0] != "b" || order[1] != "c" {
		t.Fatalf("run_order(b): %v err=%v", order, err)
	}
}

func TestRuntimeHandleErrors(t *testing.T) {
	_, err := NewRuntime(
		[]CompartmentConfig{{Name: "a"}},
		[][2]string{{"a", "nope"}},
	)
	if err == nil {
		t.Fatal("expected NewRuntime to fail for unknown edge target")
	}
	rt, err := NewRuntime([]CompartmentConfig{{Name: "a"}}, nil)
	if err != nil {
		t.Fatalf("NewRuntime: %v", err)
	}
	rt.Free()
	rt.Free()
}

func TestRuntimeHandleConcurrent(t *testing.T) {
	configs := []CompartmentConfig{
		{Name: "a", AllowOutboundTo: []string{"b"}},
		{Name: "b"},
		{Name: "c", AllowInboundFrom: []string{}},
	}
	rt, err := NewRuntime(configs, [][2]string{{"a", "b"}})
	if err != nil {
		t.Fatalf("NewRuntime: %v", err)
	}
	defer rt.Free()

	var wg sync.WaitGroup
	errCh := make(chan error, 8)
	for g := 0; g < 8; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 200; i++ {
				ok, err := rt.CanRoute("a", "b")
				if err != nil || !ok {
					errCh <- err
					return
				}
				ok, err = rt.CanRoute("b", "c")
				if err != nil || ok {
					errCh <- err
					return
				}
				order, err := rt.RunOrder("")
				if err != nil || len(order) != 3 {
					errCh <- err
					return
				}
			}
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		if err != nil {
			t.Fatalf("concurrent handle use failed: %v", err)
		}
	}
}

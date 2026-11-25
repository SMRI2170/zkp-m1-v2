// Private field-input constraint check. Emits ONLY aggregate counts, no witness/proof.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	draft "uav/research/rssi-circuit-draft"
)

func run() error {
	input := flag.String("input", "", "owner-private captures JSON only")
	output := flag.String("output", "", "public aggregate report")
	flag.Parse()
	logger.Disable()
	path, err := filepath.Abs(*input)
	if err != nil {
		return fmt.Errorf("private path")
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil || resolved != path || !strings.HasPrefix(path, captureRoot()) {
		return fmt.Errorf("private nonsymlink captures input required")
	}
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || info.Size() > 4<<20 {
		return fmt.Errorf("owner-private regular input required")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("private input read failed")
	}
	var in struct {
		Rows []draft.EnvelopeInput `json:"rows"`
	}
	if err = json.Unmarshal(data, &in); err != nil {
		return fmt.Errorf("private JSON shape invalid")
	}
	if len(in.Rows) == 0 || len(in.Rows) > 1024 {
		return fmt.Errorf("row budget")
	}
	p, err := draft.FrozenEnvelope()
	if err != nil {
		return err
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &draft.CalibratedCircuit{})
	if err != nil {
		return fmt.Errorf("compile failed")
	}
	count := [3]int{}
	for i, row := range in.Rows {
		status, err := draft.EvaluateEnvelope(p, row)
		if err != nil {
			return fmt.Errorf("input rejected at anonymous row %d", i)
		}
		if status != row.ExpectedStatus {
			return fmt.Errorf("Python/Go mismatch at anonymous row %d", i)
		}
		c, err := draft.EnvelopeAssignment(p, row, draft.StatementContext{Session: big.NewInt(1), FrameID: big.NewInt(1), ClaimToken: big.NewInt(int64(i + 1)), Nonce: big.NewInt(12345)})
		if err != nil {
			return fmt.Errorf("assignment rejected at anonymous row %d", i)
		}
		w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
		if err != nil {
			return fmt.Errorf("witness rejected at anonymous row %d", i)
		}
		if err = cs.IsSolved(w); err != nil {
			return fmt.Errorf("constraint check rejected anonymous row %d; details withheld", i)
		}
		count[status]++
	}
	b, _ := json.MarshalIndent(map[string]interface{}{"scope": "private field-derived geometry; conditional model constraints only, not a field proof", "rows": len(in.Rows), "python_go_circuit_match": true, "statuses_consistent_alarm_hold": count, "constraints": cs.GetNbConstraints(), "setup_executed": false, "proof_generated": false, "field_values_published": false}, "", "  ")
	file, err := os.OpenFile(*output, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return fmt.Errorf("fresh aggregate output required")
	}
	defer file.Close()
	if _, err := file.Write(append(b, '\n')); err != nil {
		return fmt.Errorf("aggregate output write failed")
	}
	fmt.Printf("checked %d private rows; no witness/proof files written\n", len(in.Rows))
	return nil
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func captureRoot() string {
	root, err := filepath.Abs("../..")
	if err != nil {
		return "\x00"
	}
	return filepath.Join(root, "captures") + string(filepath.Separator)
}

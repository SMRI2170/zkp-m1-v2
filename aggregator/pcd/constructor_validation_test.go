package pcd

import "testing"

func TestRecursiveCircuitConstructorsRejectNilCCS(t *testing.T) {
	tests := []struct {
		name string
		call func() error
	}{
		{name: "BridgeBW", call: func() error { _, err := NewBridgeBW(nil, nil); return err }},
		{name: "NodeBLS", call: func() error { _, err := NewNodeBLS(nil, nil); return err }},
		{name: "NodeBW", call: func() error { _, err := NewNodeBW(nil, nil); return err }},
		{name: "PromoteBLS", call: func() error { _, err := NewPromoteBLS(nil, nil); return err }},
		{name: "FinalBN", call: func() error { _, err := NewFinalBN(nil, nil); return err }},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := tt.call(); err == nil {
				t.Fatal("expected constructor to reject a nil constraint system")
			}
		})
	}
}

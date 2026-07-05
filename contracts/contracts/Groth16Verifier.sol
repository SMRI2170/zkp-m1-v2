// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract Groth16Verifier {
    // Scalar field size
    uint256 constant r    = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q   = 21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax  = 533828684528811257069605558286943386165344793282421908410126823062460109762;
    uint256 constant alphay  = 14848184660961939204081664296791948099397049309118739344166314932015084900556;
    uint256 constant betax1  = 20201885785304738474462471202925481499366071549347816401197736808605572639697;
    uint256 constant betax2  = 19578742533825623165224586855991014686863255097694521549911307315889997795357;
    uint256 constant betay1  = 10520936694478949579122059556763197647303124733163433183781750007509939131312;
    uint256 constant betay2  = 6491940229284957501999868729888675369878251647823756538597799888878876463338;
    uint256 constant gammax1 = 11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 = 10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 = 4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 = 8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 = 6856464971010691228279425839043746224934396018521067509783140799921693254320;
    uint256 constant deltax2 = 13636650534797804036290141087901712627454619499962979224611296273436080459219;
    uint256 constant deltay1 = 12472778075849166956359601927141158178263419610118916238836711282473198695906;
    uint256 constant deltay2 = 13516638544976609830957087813398456357068705875966869393059932686095675075104;

    
    uint256 constant IC0x = 19176674260089115159776575378844981307198985673934722447316524971394768520650;
    uint256 constant IC0y = 19203610392737795788963996074729088992249051545071309068924668826063158349585;
    
    uint256 constant IC1x = 16834975805907325475922666613718061674018161699736945926513539845263927529848;
    uint256 constant IC1y = 13014963066519933517572771075463835730239349574996927847546823359800766883355;
    
    uint256 constant IC2x = 8552533409160967859114968154382545261608770151897411406592049461032203444958;
    uint256 constant IC2y = 6542753225314153998447553177544724019589945084221097560962119795351767959733;
    
    uint256 constant IC3x = 20925008730004212738698742985542798820659573186761553429458418450905683784743;
    uint256 constant IC3y = 5221208551122849654657917360021620402538815272269860021681227510979880313838;
    
    uint256 constant IC4x = 11001892807346009139655885271377582674004551655697522109062532271923091603635;
    uint256 constant IC4y = 6562550933438148497572532612304930772062000558788579218042324160970522115702;
    
    uint256 constant IC5x = 3091010362305105346346798067250879892828990190966954747030039898703212658045;
    uint256 constant IC5y = 4252511278946767312393895880629382522847631781317793299830633499910841589774;
    
    uint256 constant IC6x = 11574784263160259315156775068630804316707598627122407004413798048528863402796;
    uint256 constant IC6y = 4629269352201705758392627437639080322222948848602756774574247862827326710301;
    
    uint256 constant IC7x = 13745625251828177796315225003080095032336632779721972183385184318657851714117;
    uint256 constant IC7y = 13975413991174442544231381460726277601743687458580774334217434155133281562457;
    
    uint256 constant IC8x = 3664256621502542134952545521462772419036923122291378498878554922233908164102;
    uint256 constant IC8y = 1048347463220676239565757672035236784398908339230794605769866199415569760238;
    
    uint256 constant IC9x = 6279150979375433905752088953536124783820146925739459703451732809535170219038;
    uint256 constant IC9y = 20671415715256078128456421585156274810717224952842572379420277578745521098404;
    
    uint256 constant IC10x = 2849520685345624601741665519322646293912121077753237159270743352108577397726;
    uint256 constant IC10y = 14683532697433051643174665236811814059525181979613189681708232269863497788940;
    
    uint256 constant IC11x = 11032975125790061005083009170858833718250104469633917019345468686090394611331;
    uint256 constant IC11y = 5112707177062436781253879779598960081090121262142549807249977898263657367966;
    
    uint256 constant IC12x = 20583643678121056136953967930348454233246509320345874592040161465830696579027;
    uint256 constant IC12y = 19121441775235180177055428984042534812277580223211947955306201972748328557203;
    
    uint256 constant IC13x = 7053424310881858917862964035064223145195417374293378074321408746772358067298;
    uint256 constant IC13y = 2233449092235624477027385768827600000617580083900209184573723217556994466174;
    
    uint256 constant IC14x = 12313192841874639645618298953062248229225022078244622257726932678156995208276;
    uint256 constant IC14y = 4998784961904526730543323244092685286837729851724745375538955369294944526283;
    
 
    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(uint[2] calldata _pA, uint[2][2] calldata _pB, uint[2] calldata _pC, uint[14] calldata _pubSignals) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }
            
            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x
                
                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))
                
                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))
                
                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))
                
                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))
                
                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))
                
                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))
                
                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))
                
                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))
                
                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))
                
                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))
                
                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))
                
                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))
                
                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))
                
                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))
                

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))


                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)


                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F
            
            checkField(calldataload(add(_pubSignals, 0)))
            
            checkField(calldataload(add(_pubSignals, 32)))
            
            checkField(calldataload(add(_pubSignals, 64)))
            
            checkField(calldataload(add(_pubSignals, 96)))
            
            checkField(calldataload(add(_pubSignals, 128)))
            
            checkField(calldataload(add(_pubSignals, 160)))
            
            checkField(calldataload(add(_pubSignals, 192)))
            
            checkField(calldataload(add(_pubSignals, 224)))
            
            checkField(calldataload(add(_pubSignals, 256)))
            
            checkField(calldataload(add(_pubSignals, 288)))
            
            checkField(calldataload(add(_pubSignals, 320)))
            
            checkField(calldataload(add(_pubSignals, 352)))
            
            checkField(calldataload(add(_pubSignals, 384)))
            
            checkField(calldataload(add(_pubSignals, 416)))
            

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
             return(0, 0x20)
         }
     }
 }
